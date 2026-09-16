"""Vision wrapper modules (camera capture, color detection, ...).

Like src/hardware/, each module here is small and single-purpose so it can
be taught one piece at a time in a notebook. This package is READ-ONLY with
respect to the robot - it only ever looks at camera frames, it never drives
a motor or an LED directly. Composing "camera sees color X -> LED shows
color X" is notebook-level teaching logic that lives in a notebook, not in
this package - see src/hardware/rgb_led.py for the actuation side.
"""
