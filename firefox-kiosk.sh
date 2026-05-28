#!/bin/bash

until /usr/bin/firefox -kiosk http://localhost:8080/display; do
	echo "Firefox has just crashed with exit code $?. Starting again" >&2
	sleep 1
done
