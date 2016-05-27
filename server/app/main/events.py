import gevent
from flask import request
from flask.ext.socketio import emit

from app.main.SocketIOMJPEGBroadcaster import SocketIOMJPEGBroadcaster
from app.main.SocketIOMPEGBroadcaster import SocketIOMPEGBroadcaster
from app.main.SocketIOMPEGRedisBroadcaster import SocketIOMPEGRedisBroadcaster
from app.main.redis_funcs import mark_active
from .. import socketio


@socketio.on('start', namespace='/mjpeg')
def mjpeg_stream_start(data):
    print('[mjpeg]: Starting MJPEG stream')

    cam = data['cam']

    # request.sid contains the unique identifier of the client that sent ht events, which is also the channel
    # name that shoul enable us ot send messages specifically to that client.
    client_sid = request.sid

    # Start the broadcaster
    t = SocketIOMJPEGBroadcaster(cam, client_sid)
    gevent.spawn(t.run)


@socketio.on('start', namespace='/mpeg')
def mpeg_stream_start(data):
    print('[mpeg]: Starting MPEG stream')

    cam = data['cam']

    # Mark in Redis the stream as alive.
    mark_active(cam, 'mpeg')

    # Supposedly request.sid contains the unique identifier of the client that sent the events, which is also the
    # channel name that should enable us to send messages specifically to that client.
    client_sid = request.sid

    # Start the broadcaster
    # Though there might be some more efficient ways through broadcasting, for now we create a broadcaster greenlet
    # for every client, and we pass it the client_sid so that it can send data to a specific client.
    t = SocketIOMPEGRedisBroadcaster(cam, client_sid)
    gevent.spawn(t.run)


# TODO: Connected events are actually not needed. If socket.io works without them, they should be removed.

@socketio.on('connected', namespace='/mpeg')
def mpeg_stream_connected():
    print('[mpeg]: Connected event received')


@socketio.on('connected', namespace='/mjpeg_streams')
def mjpeg_stream_connected():
    print('[mjpeg]: Connected to MJPEG stream')



# TODO: The ones below are experiments, and they should be removed once the main widgets work.
@socketio.on('connected', namespace='/chat')
def handle_my_custom_event(data):
    print('Received: ' + type(data) + ' : ' + data)
    emit('status', {'msg': 'ok'})


@socketio.on('hello', namespace='/chat')
def handle_hello(data):
    print("HELLO WAS RECEIVED")


@socketio.on('hello')
def handle_hello_nons():
    print("HELLO WITH NO NS")


@socketio.on('connected', namespace='/stream')
def connected_stream(data):
    print('Connected to stream')
    emit('status', {'msg': 'connected indeed'})

    # Start the broadcaster
    t = SocketIOMPEGBroadcaster()
    gevent.spawn(t.run)
