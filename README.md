# midi_player
Play midi files on the Raspberry Pi using multiple piezo buzzers, wiringpi and py-midicsv.<br/>
Requires Python 3.<br/>
You also need <code>pip3 install wiringpi py-midicsv</code>.<br/>
Comment if something's wrong.<br/>
Ran fine for me on a Pi 3B+.<br/>
Example playlist on Youtube: https://www.youtube.com/playlist?list=PLDa4Vj43E2e9bdgJLPYenDJvnHyA-Bi5w<br/>
You can use this to get smoother notes: https://unix.stackexchange.com/questions/204334/can-one-core-on-a-multicore-linux-system-be-dedicated-to-one-user-space-app, but dedicate 2 cores, because with 1 core I got vibrato on some notes.
