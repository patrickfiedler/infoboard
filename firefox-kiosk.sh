#!/bin/bash

until /usr/bin/firefox -kiosk http://1.2.3.4:8001/display; do
	echo "Firefox has just crashed with exit code $?. Starting again" >&2
	sleep 1
done
