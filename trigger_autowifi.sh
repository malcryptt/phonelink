#!/bin/bash
export XDG_RUNTIME_DIR=/run/user/1000
# Fire up the systemd task in a detached fashion
systemctl --user start phonelink-autowifi.service --no-block
