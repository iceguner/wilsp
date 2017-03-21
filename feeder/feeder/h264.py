import traceback

import gevent
import re

from gevent import subprocess
import redis


class H264Feeder(object):
    """
    The H264 feeder will control a ffmpeg instance, direct it through stdout pipe, and push it to redis.
    the stream in REDIS. An MJPEG source from the webcam is currently REQUIRED.
    """

    def __init__(self, rdb: redis.StrictRedis, redis_prefix: str, cam_name: str, mjpeg_source: str, ffmpeg_bin: str):
        self._g = []
        self._cam_name = cam_name
        self._mjpeg_source = mjpeg_source
        self._rdb = rdb
        self._redis_prefix = redis_prefix

        self._ffmpeg_bin = ffmpeg_bin

    def _run(self):
        # Redis channel
        redis_channel = '{}/h264'.format(self._cam_name)

        # Eventlet cannot greenify subprocess, so we will call ffmpeg from a different thread.

        def run_ffmpeg():

            # For debugging only.
            # self._mjpeg_source = "http://cams.weblab.deusto.es/webcam/fishtank1/video.mjpeg"

            # Interesting command for testing: avconv -r 30 -f mjpeg -i http://cams.weblab.deusto.es/webcam/fishtank1/video.mjpeg -c:v libx264 -preset:v ultrafast -r 30 -f h264 pipe:1 | ffplay -i -

            # The following command works fine but seems to have a relatively high latency, especially for lower framerates.
            # Seems to have around 2.2 s delay (with respect to the direct MJPEG stream)
            # ffmpeg_command = [self._ffmpeg_bin, '-r', '30', '-f', 'mjpeg', '-i', self._mjpeg_source, '-c:v', 'libx264', '-preset:v', 'ultrafast', '-r', '5', "-f", "h264", "pipe:1"]

            # The following command has a very low latency but is potentially less efficient.
            # Seems to have around 0.8 seconds delay.
            ffmpeg_command = [self._ffmpeg_bin, '-r', '30', '-f', 'mjpeg', '-i', self._mjpeg_source, '-flags', '+low_delay',
                              '-probesize', '32', '-c:v', 'libx264', '-tune', 'zerolatency', '-preset:v', 'ultrafast', '-r',
                              '30', "-f", "h264", "-s", "640x480", "-b:v", "1500k",
                              #"-keyint_min", "1",
                              "-g", "100",  # This parameter is important: Every 100 frames at most it will send an I frame that initializes the stream
                              # "-profile:v", "baseline",
                              "-pix_fmt", "yuv420p",  # This parameter on 14 mar 2017 an fishtank webcam it has started to be necessary. Maybe because without it, it doesnt use the baseline profile.
                              "pipe:1"]

            print("Running FFMPEG command: {}".format(ffmpeg_command))

            p = subprocess.Popen(ffmpeg_command, stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.PIPE)


            # EXP1: Streaming the test.h264 sample works fine.
            # EXP2: H.264 to file by ffmpeg, and written H.264 to file after piping, seem to be the same binary file: WORKS FINE.
            # EXP3: Streaming file that has been generated after piping: DOES NOT WORK.
            # EXP4: Streaming file cdout.h264 that has been generated by avconv gen.h264:
            # Hypothesis: Maybe the test file has been generated with ffmpeg instead of avconv, or with a different profile.
            # CONCLUSION: THAT WAS INDEED THE CASE. -profile:v baseline works. Maybe using presets would too.

            # Issue: Current fishtank camera seems to not work from the client-side unless -pix_fmt yuv240p is specified".


            # self._data = open("/home/lrg/repos/player/samples/test.h264", "rb").read()
            # self._data = open("/tmp/piped.h264", "rb").read()
            # self._data = open("/tmp/gen.h264", "rb").read()
            i = 0

            def myreadlines(f, newline):
                """
                Custom readlines to use a specific terminator: ffmpeg uses ^M (\r) to separate the line with the stats.
                :param f:
                :param newline:
                :return:
                """
                buf = bytes()
                while True:
                    while newline in buf:
                        pos = buf.index(newline)
                        yield buf[:pos]
                        buf = buf[pos + len(newline):]
                    chunk = f.read(50)  # 50 bytes buffer: Appropriate for the amount of data we tend to receive.
                    if not chunk:
                        yield buf
                        break
                    buf += chunk

            def handle_stderr(err):
                """
                Handles the stderr stream, which in the case of ffmpeg does not only contain errors, but stats.
                We will periodically push the fps to redis. (Trying to update only every so often to decrease the potential
                impact on performance).
                :param err:
                :param queue:
                :return:
                """
                base_key = "{}:cams:{}:stats:".format(self._redis_prefix, self._cam_name)
                fps_key = base_key+"fps"

                fps_list = []
                for line in myreadlines(err, b'\r'):
                    try:
                        # Try to extract FPS
                        results = re.findall(r"fps=\s([0-9]+)\s", line.decode('utf-8'))
                        if len(results) > 0:
                            fps = int(results[0])
                            fps_list.append(fps)

                            if len(fps_list) >= 5:
                                avg = sum(fps_list) / len(fps_list)
                                fps_list = []
                                self._rdb.setex(fps_key, 30, avg)
                    except:
                        traceback.print_exc()
                err.close()

            stderr_handler = gevent.spawn(handle_stderr, p.stderr)
            self._g.append(stderr_handler)

            while True:
                try:
                    packet = p.stdout.read(2048)
                    n = len(packet)
                    if n > 0:
                        # It is noteworthy that, as of now, the packets are a stream. An alternative would be to split the frames
                        # here. This is more efficient from a networking perspective, but it probably transfers some work
                        # to the Redis listeners.
                        self._rdb.publish(redis_channel, packet)
                    elif n != 2048:
                        return 2
                except ValueError as ex:
                    return 1

        run_ffmpeg()

        print("H.264 greenlet is OUT")

    def start(self):
        g = gevent.spawn(self._run)
        self._g.append(g)
