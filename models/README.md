# Models

Three files go in this folder. None are in the repo: two are downloads, and one is made on your Mac.

| File | What it is | Get it |
|---|---|---|
| `ggml-large-v3-turbo-q5_0.bin` | Whisper large-v3-turbo, the speech model (574 MB, MIT) | [Download from whisper.cpp on Hugging Face](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin) |
| `ggml-silero-v5.1.2.bin` | Silero, which finds the speech and skips silence (1 MB, MIT) | [Download from ggml-org on Hugging Face](https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin) |
| `warm.wav` | A short spoken clip that keeps the speech model ready | Made by the setup steps with your Mac's own voice |

From the repo folder:

```bash
curl -L -o models/ggml-large-v3-turbo-q5_0.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin
curl -L -o models/ggml-silero-v5.1.2.bin https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v5.1.2.bin
say -o /tmp/warm.aiff "Testing one two three." && ffmpeg -loglevel error -y -i /tmp/warm.aiff -ar 16000 -ac 1 models/warm.wav
```
