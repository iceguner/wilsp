from abc import abstractmethod
import io
import time

import gevent
import redis
from PIL import Image

from feeder import config


class CamFeeder(object):
    """
    CamFeeder abstract base class. Children CamFeeders should at least implement the _run_until_inactive method.
    The base class handles FPS control and activity/inactivity flow, as long as _check_active() is periodically called.

    TO-DO: max_fps and url should probably be removed from the base class.
    """

    IMAGE_EXPIRE_TIME = config.IMAGE_EXPIRE_TIME
    STATS_PUSH_WAIT = 1
    SLEEP_WHEN_INACTIVE = 0.01

    ########################################################
    # PUBLIC API
    ########################################################

    def __init__(self, rdb: redis.StrictRedis, redis_prefix: str, cam_name: str, url: str, max_fps: int,
                 rotation: float = None):
        self._g = []  # type: [gevent.greenlet.Greenlet]
        self._rdb = rdb  # type: redis.StrictRedis
        self._redis_prefix = redis_prefix
        self._url = url
        self._cam_name = cam_name
        self._rotation = rotation if rotation is not None else 0
        self._max_fps = max_fps

        self._frames_this_cycle = 0
        self._active = None  # Whether the camera is active or not (being used, according to redis)
        self._active_since = None  # Timestamp when we last became active

    def get_current_fps(self) -> float:
        """
        Retrieves the current FPS for this active cycle, measured as the number
        of frames rendered so far in the cycle divided by the elapsed active time.
        :return:
        """
        if self._active_since is None:
            return 0
        elapsed = time.time() - self._active_since
        if elapsed == 0:
            return 0
        return self._frames_this_cycle / elapsed

    def start(self):
        """
        Starts running the greenlet.
        :return:
        """
        g = gevent.spawn(self._run)
        self._g.append(g)

        # Start the stats pusher as well.
        g = gevent.spawn(self._run_stats_greenthread)
        self._g.append(g)

    ########################################################
    # PRIVATE API
    ########################################################

    def _run_stats_greenthread(self) -> None:
        """
        Calls every so often the '_push_stats' method.
        :return:
        """
        while True:
            self._push_stats()
            gevent.sleep(CamFeeder.STATS_PUSH_WAIT)

    def _push_stats(self) -> None:
        """
        Push stats to the REDIS server.
        :return:
        """
        base_key = "{}:cams:{}:stats:".format(self._redis_prefix, self._cam_name)

        self._rdb.setex(base_key + 'cycle_frames', CamFeeder.IMAGE_EXPIRE_TIME * 3, self._frames_this_cycle)

        if self._active_since is not None:
            self._rdb.setex(base_key + 'cycle_elapsed', CamFeeder.IMAGE_EXPIRE_TIME * 3, time.time() - self._active_since)


    @abstractmethod
    def _run_until_inactive(self) -> None:  # pragma: no cover
        """
        Runs, feeding images to redis, until it is time to become inactive.
        :return:
        """
        pass

    def _wait_until_active(self) -> None:
        """
        Waits until it is time to become active. In order to do so, checks often
        whether someone has started using the webcam.
        :return:
        """
        while not self._active:
            self._check_active()
            if not self._active:
                gevent.sleep(CamFeeder.SLEEP_WHEN_INACTIVE)

    def _run(self) -> None:
        """
        Greenlet's main thread. Will loop forever between the active and inactive loops. Does not add sleep times.
        :return:
        """
        while True:
            if self._active:
                # We are becoming active.
                self._frames_this_cycle = 0
                self._active_since = time.time()
                self._run_until_inactive()
            if not self._active:
                self._wait_until_active()

    def _check_active(self) -> None:
        """
        Checks whether we should change our activity status, and thus change the current mode.
        :return:
        """
        active = self._rdb.get("{}:cams:{}:active".format(self._redis_prefix, self._cam_name))
        self._active = active is not None

    def _notify_frame_put(self) -> None:
        """
        Should be called just after a new frame is put into redis so that internal FPS calculations, etc,
        can be carried out automatically.
        :return:
        """
        self._frames_this_cycle += 1

    @staticmethod
    def _rotated(data: bytes, rotation: float) -> bytes:
        """
        Rotates the given image.
        :param data: The image as a full image file (such as a full JPG).
        :param rotation: Rotation to apply.
        :return: Full resulting jpeg image, expanded as necessary.
        """
        if rotation == 0:
            return data

        sio_in = io.BytesIO(data)
        img = Image.open(sio_in)  # type: Image
        img = img.rotate(rotation, expand=True)
        sio_out = io.BytesIO()
        img.save(sio_out, 'jpeg')
        data = sio_out.getvalue()
        img.close()

        return data

    def _put_frame(self, frame: bytes) -> None:
        """
        Stores the specified frame into redis.
        :param frame: Frame binary contents (full image)
        :return:
        """

        # Set a relatively early expire to ensure that wrong images do not stay for long
        self._rdb.setex("{}:cams:{}:lastframe".format(self._redis_prefix, self._cam_name), CamFeeder.IMAGE_EXPIRE_TIME, frame)

        self._notify_frame_put()


if __name__ == "__main__": # pragma: no cover
    import doctest
    doctest.testmod()