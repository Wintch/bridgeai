# ComfyUI benchmark image: tts-chatterbox (conda python 3.11) with a current torch + ComfyUI requirements; code mounted
FROM tts-chatterbox:latest
COPY requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir -q torch==2.9.1 torchvision==0.24.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cu128
RUN grep -vE "^(torch|torchvision|torchaudio)([<>= ]|$)" /tmp/req.txt > /tmp/r.txt && pip install --no-cache-dir -q -r /tmp/r.txt
ENTRYPOINT []
