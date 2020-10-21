#!/usr/bin/python3
import time
import os
import random
import argparse
import py_midicsv
import wiringpi

def parse_arguments():
    parser = argparse.ArgumentParser(description="play midi files on RaspberryPi")
    parser.add_argument("input_files", nargs="*", default = ['.'], help="midi file(s) to play, or dir(s) to get midi(s) from, random play if more midis are available")
    parser.add_argument("-c", "--count", type=int, default = 1, metavar="count", help="specify the maximum number of midi files to play, default is 1")
    parser.add_argument("-s", "--speed", type=float, default = 1, metavar="multiplier", help="makes the music speed slower or faster")
    parser.add_argument("-S", "--shiftpitch", type=int, default = 0, metavar="semitones", help="makes the music pitch lower or higher")
    parser.add_argument("-p", "--pedal", action='store_true', dest="use_pedal", help="it uses pedal information")
    parser.add_argument("-n", "--nonverbose", action='store_true', dest="is_silent", help="it doesn't print to stdout")
    parser.add_argument("-P", "--pins", default = "21,20,16,12,1,7,8,25,24,23", metavar="numbers", help="determines the number of piezo speakers too, default is \"21,20,16,12,1,7,8,25,24,23\"")
    return vars(parser.parse_args())

def get_possible_midi_files(input_files, is_silent):
    new_input_files = []
    for i in input_files:
        if i[-4:] == ".mid":
            if os.path.isfile(i):
                new_input_files.append(i)
            elif not is_silent:
                print("didn't find midi file: " + i)
        elif os.path.isdir(i):
            new_input_files += [os.path.join(i, j) for j in os.listdir(i) if j[-4:] == ".mid"]
        elif not is_silent:
            print("didn't find midi file nor dir named: " + i)
    return new_input_files

def import_midi_file(input_file, is_silent):
    if not is_silent:
        print("importing midi file: " + input_file)
    csv_strings = py_midicsv.midi_to_csv(input_file)
    return [i[:-1].split(", ") for i in csv_strings]

def pedal_to_noteoff(data, use_pedal):
    if not use_pedal:
        return data, 0
    pedals = []
    waiting_notes = []
    new_data = []
    sustained_notes = 0
    for i in data:
        if i[2] == "Control_c" and i[4] == "64":
            if int(i[5]) > 63:
                pedals.append(i[3])
            else:
                if i[3] in pedals:
                    pedals.remove(i[3])
                new_data.extend([j[0], i[1], j[2], j[3], j[4], j[5]] for j in waiting_notes if j[3] == i[3])
                waiting_notes = list(filter(lambda x : x[3] != i[3], waiting_notes))
        if ((i[2] == "Note_on_c" and i[5] == "0") or i[2] == "Note_off_c") and i[3] in pedals:
            waiting_notes.append(i)
            sustained_notes += 1
        else:
            new_data.append(i)
    return new_data, sustained_notes

def convert_time(data, speed):
    clock_per_quarter_note = int(data[0][5])
    new_data = []
    previous_time = 0
    time_since_note = 0
    tempo = 0
    length = 0
    note_count = 0
    for i in data:
        delta = tempo * (int(i[1]) - previous_time) / speed / clock_per_quarter_note / 1000000
        previous_time = int(i[1])
        time_since_note += delta
        length += delta
        if i[2] == "Tempo":
            tempo = int(i[3])
        if i[2] == "Note_on_c" and i[5] != "0" and i[3] != "9":
            new_data.append([time_since_note, True, int(i[4])])
            time_since_note = 0
            note_count += 1
        if ((i[2] == "Note_on_c" and i[5] == "0") or i[2] == "Note_off_c") and i[3] != "9":
            new_data.append([time_since_note, False, int(i[4])])
            time_since_note = 0
    return new_data, length, note_count

def calculate_hz(midi_note, shiftpitch):
    if midi_note < 45:
        return int(440*2**((midi_note+shiftpitch-69)/12))
    else:
        return int(440*2**((midi_note+shiftpitch-69)/12)*(((midi_note-45)*0.005)**2+1))

def restrict_number_of_notes(data, pins, shiftpitch): #data: [[s az előzőtől, on-e, hgmagasság],[]]
    new_data = []           #[[s az előzőtől, pin, hgmagasság],[]]
    sounding_notes = []     #[[pin, hgmagasság],[]]
    bad_offs = []           #[kitolt hgmagasság, ...]
    delay_until_good_off = 0
    bad_offs_count = 0
    for i in data:
        if i[1]:
            if len(pins) - 1 == len(sounding_notes):
                shifted_note = sounding_notes.pop(0)
                bad_offs.append(shifted_note[1])
                sounding_notes.append([shifted_note[0], i[2]])
                new_data.append([i[0] + delay_until_good_off, shifted_note[0], calculate_hz(i[2], shiftpitch)])
                delay_until_good_off = 0
                bad_offs_count += 1
            else:
                for j in pins:
                    if not any(j == k[0] for k in sounding_notes):
                        sounding_notes.append([j, i[2]])
                        new_data.append([i[0] + delay_until_good_off, j, calculate_hz(i[2], shiftpitch)])
                        delay_until_good_off = 0
                        break
        else:
            if i[2] in bad_offs:
                bad_offs.remove(i[2])
                delay_until_good_off += i[0]
            else:
                for jndex, j in enumerate(sounding_notes):
                    if j[1] == i[2]:
                        shifted_note = sounding_notes.pop(jndex)
                        new_data.append([i[0] + delay_until_good_off, shifted_note[0], 0])
                        delay_until_good_off = 0
                        break
    return new_data, bad_offs_count

def show_stats(stats):
    text = "playing {} notes for {} minutes, with {} ({}%) bad offs and {} ({}%) sustained notes"
    minutes = round(stats["length"]/60, 2)
    bad_offs = (stats["bad_offs_count"], round(100 * stats["bad_offs_count"] / stats["note_count"], 1))
    sustained = (stats["sustained_notes"], round(100 * stats["sustained_notes"] / stats["note_count"], 1))
    print(text.format(stats["note_count"], minutes, bad_offs[0], bad_offs[1], sustained[0], sustained[1]))

def play(data):
    for i in data:
        time.sleep(i[0])
        wiringpi.softToneWrite(i[1], i[2])

def main():
    args = parse_arguments()
    input_files = get_possible_midi_files(args["input_files"], args["is_silent"])
    random.shuffle(input_files)
    input_files = input_files[0:args["count"]]
    pins = [int(i) for i in args["pins"].split(",")]
    wiringpi.wiringPiSetupGpio()
    [wiringpi.softToneCreate(i) for i in pins]
    for i in input_files:
        stats = {"sustained_notes": 0, "length": 0, "note_count": 0, "bad_offs_count": 0}
        data = import_midi_file(i, args["is_silent"])
        data.sort(key = lambda x: int(x[1]))
        data, stats["sustained_notes"] = pedal_to_noteoff(data, args["use_pedal"])
        data, stats["length"], stats["note_count"] = convert_time(data, args["speed"])
        data, stats["bad_offs_count"] = restrict_number_of_notes(data, pins, args["shiftpitch"])
        if not args["is_silent"]:
            show_stats(stats)
        play(data)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("interrupted by keyboard")
        raise SystemExit
