import subprocess
import eventlet
from eventlet import tpool


class H264Feeder(object):
    """
    The H264 feeder will control a ffmpeg instance, direct it through stdout pipe, and push it to redis.
    the stream in REDIS. An MJPEG source from the webcam is currently REQUIRED.
    """

    def __init__(self, rdb, cam_name, mjpeg_source, ffmpeg_bin):
        self._g = []
        self._cam_name = cam_name
        self._mjpeg_source = mjpeg_source
        self._rdb = rdb

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
                              '5', "-f", "h264", "-b:v", "1500k", "pipe:1"]

            print("Running FFMPEG command: {}".format(ffmpeg_command))

            p = subprocess.Popen(ffmpeg_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

            # EXP1: Streaming the test.h264 sample works fine.
            # EXP2: H.264 to file by ffmpeg, and written H.264 to file after piping, seem to be the same binary file: WORKS FINE.
            # EXP3: Streaming file that has been generated after piping: DOES NOT WORK.
            # EXP4: Streaming file cdout.h264 that has been generated by avconv gen.h264:
            # Hypothesis: Maybe the test file has been generated with ffmpeg instead of avconv, or with a different profile.
            # CONCLUSION: THAT WAS INDEED THE CASE. -profile:v baseline works. Maybe using presets would too.


            # self._data = open("/home/lrg/repos/player/samples/test.h264", "rb").read()
            # self._data = open("/tmp/piped.h264", "rb").read()
            # self._data = open("/tmp/gen.h264", "rb").read()
            i = 0


            while True:
                # TODO: Consider whether we should read in some other way.
                try:
                    packet = p.stdout.read(2048)
                    if len(packet) > 0:
                        # It is noteworthy that, as of now, the packets are a stream. An alternative would be to split the frames
                        # here. This is more efficient from a networking perspective, but it probably transfers some work
                        # to the Redis listeners.
                        self._rdb.publish(redis_channel, packet)
                    else:
                        return 2
                except ValueError as ex:
                    return 1

        tpool.execute(run_ffmpeg)

        print("H.264 greenlet is OUT")

    def start(self):
        g = eventlet.spawn(self._run)
        self._g.append(g)
