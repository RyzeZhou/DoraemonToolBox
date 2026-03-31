#!/bin/bash
cd "$(dirname "$0")"
exec /root/miniconda3/bin/python main.py 2>&1 | tee /tmp/gui_start_$(date +%s).log
