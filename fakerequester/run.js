var io = require('socket.io-client');
var request = require('request');
var argv = require('yargs')
	.usage('Usage: $0 -w [num] -u [u] -t [type]')
    .demandOption(['w'])
    .default({ u: "localhost:5000", t: "img"})
    .argv;


var type = argv.t;

if(type != "img" && type != "h264") {
    console.log("Unrecognized type.");
    process.exit(1);
}


var url = undefined;
if (type == "img") {
    url = "http://" + argv.u + "/cams/cams_0_0";
} else {
    url = "http://" + argv.u + "/264";
}

console.log("Starting for " + argv.w.toString() + " and type " + argv.t);


for(var i = 0; i < argv.w; i++) {

    if(type == "h264") {
        (function () {
            var socket = io.connect(url);

            socket.on('connect', function () {
                console.log("socket connected");

                socket.emit('start', {'cam': 'cam0_0'});
            });

            socket.on('disconnect', function () {
                console.log("socket disconnected");
            });

            socket.on('stream', function (arg) {
                // console.log('stream event received');
            });
        })();
    } else {
        (function() {
            var period = 1000 / 30; // 30 FPS target
            var count = 0;
            var errors = 0;
            var programStartTime = Date.now();

            var cycle = function () {
                var updateStartTime = Date.now();
                (function () {
                    request(url, function (error, response, body) {
                        if(error)
                            errors += 1;
                        else
                            count++;
                        var elapsed = Date.now() - updateStartTime;
                        var time_left = period - elapsed;

                        setTimeout(cycle, time_left);

                        console.log("Frames: " + count.toString() + " | FPS: " + (count / ((Date.now() - programStartTime) / 1000)).toString() + " | Errors: " + errors.toString());
                    });
                })();
            };

            cycle();
        })();
    }
}

