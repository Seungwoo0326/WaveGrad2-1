import os
import random
import json

import tgt
import librosa
import numpy as np
from scipy.io import wavfile
from tqdm import tqdm

random.seed(1234)


class Preprocessor:
    def __init__(self, config):
        self.config = config
        self.in_dir = config["path"]["raw_path"]
        self.out_dir = config["path"]["preprocessed_path"]
        self.val_size = config["preprocessing"]["val_size"]
        self.sampling_rate = config["preprocessing"]["audio"]["sampling_rate"]
        self.hop_length = config["preprocessing"]["stft"]["hop_length"]

    def build_from_path(self):
        os.makedirs((os.path.join(self.out_dir, "wav")), exist_ok=True)
        os.makedirs((os.path.join(self.out_dir, "duration")), exist_ok=True)
        # os.makedirs((os.path.join(self.out_dir, "duration_up")), exist_ok=True)

        print("Processing Data ...")
        out = list()
        n_sec = 0

        # Compute data
        speakers = {}
        for i, speaker in enumerate(tqdm(os.listdir(self.in_dir))):
            speakers[speaker] = i
            for wav_name in tqdm(os.listdir(os.path.join(self.in_dir, speaker))):
                if ".wav" not in wav_name:
                    continue

                basename = wav_name.split(".")[0]
                tg_path = os.path.join(
                    self.out_dir, "TextGrid", speaker, "{}.TextGrid".format(basename)
                )
                if os.path.exists(tg_path):
                    ret = self.process_utterance(speaker, basename)
                    if ret is None:
                        continue
                    else:
                        info, n = ret
                    out.append(info)

                n_sec += n

        # Save files
        with open(os.path.join(self.out_dir, "speakers.json"), "w") as f:
            f.write(json.dumps(speakers))

        print(
            "Total time: {} hours".format(
                n_sec / 3600
            )
        )

        random.shuffle(out)
        out = [r for r in out if r is not None]

        # Write metadata
        with open(os.path.join(self.out_dir, "train.txt"), "w", encoding="utf-8") as f:
            for m in out[self.val_size :]:
                f.write(m + "\n")
        with open(os.path.join(self.out_dir, "val.txt"), "w", encoding="utf-8") as f:
            for m in out[: self.val_size]:
                f.write(m + "\n")

        return out

    def process_utterance(self, speaker, basename):
        wav_path = os.path.join(self.in_dir, speaker, "{}.wav".format(basename))
        text_path = os.path.join(self.in_dir, speaker, "{}.lab".format(basename))
        tg_path = os.path.join(
            self.out_dir, "TextGrid", speaker, "{}.TextGrid".format(basename)
        )

        # Get alignments
        textgrid = tgt.io.read_textgrid(tg_path)
        phone, duration, _, start, end = self.get_alignment(
            textgrid.get_tier_by_name("phones")
        )
        text = "{" + " ".join(phone) + "}"
        if start >= end:
            return None

        # Read and trim wav files
        wav, _ = librosa.load(wav_path)
        wav = wav[
            int(self.sampling_rate * start) : int(self.sampling_rate * end)
        ].astype(np.float32)

        # # A single frame padding
        # if sum(duration_up) > wav.shape[0]:
        #     wav = np.concatenate((wav, np.array([0.])))
        # elif sum(duration_up) < wav.shape[0]:
        #     wav = wav[:-1]

        # assert sum(duration_up) == wav.shape[0], \
        #     "{} is wrongly processed in length!: {} != {}".format(basename, sum(duration_up), wav.shape[0])

        # Read raw text
        with open(text_path, "r") as f:
            raw_text = f.readline().strip("\n")

        # Save files
        dur_filename = "{}-duration-{}.npy".format(speaker, basename)
        np.save(os.path.join(self.out_dir, "duration", dur_filename), duration)

        # dur_up_filename = "{}-duration_up-{}.npy".format(speaker, basename)
        # np.save(os.path.join(self.out_dir, "duration_up", dur_up_filename), duration_up)

        wav_filename = "{}-wav-{}.wav".format(speaker, basename)
        wavfile.write(
            os.path.join(self.out_dir, "wav", wav_filename),
            self.sampling_rate,
            wav,
        )

        return (
            "|".join([basename, speaker, text, raw_text]),
            wav.shape[0]/self.sampling_rate,
        )

    def get_alignment(self, tier):
        sil_phones = ["sil", "sp", "spn"]

        phones = []
        durations = []
        durations_up = []
        start_time = 0
        end_time = 0
        end_idx = 0
        for t in tier._objects:
            s, e, p = t.start_time, t.end_time, t.text

            # Trim leading silences
            if phones == []:
                if p in sil_phones:
                    continue
                else:
                    start_time = s

            if p not in sil_phones:
                # For ordinary phones
                phones.append(p)
                end_time = e
                end_idx = len(phones)
            else:
                # For silent phones
                phones.append(p)

            durations.append(
                int(
                    np.round(e * self.sampling_rate / self.hop_length)
                    - np.round(s * self.sampling_rate / self.hop_length)
                )
            )
            # durations_up.append(
            #     int(
            #         np.round(e * self.sampling_rate)
            #         - np.round(s * self.sampling_rate)
            #     )
            # )

        # Trim tailing silences
        phones = phones[:end_idx]
        durations = durations[:end_idx]
        # durations_up = durations_up[:end_idx]

        return phones, durations, durations_up, start_time, end_time
