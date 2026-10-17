# Rekomendacje (RAG): Lambda z obrazu kontenera (arm64) - src/recommender_api + pakiet recommender/.
# Budowanie z katalogu głównego repo (scripts/push-images.sh recommender):
#   docker build --platform linux/arm64 --provenance=false -f src/recommender_api/Dockerfile .
FROM public.ecr.aws/lambda/python:3.13

# = DEFAULT_MODEL w recommender/embedder/model.py
ARG EMBEDDING_MODEL_NAME=sentence-transformers/paraphrase-multilingual-mpnet-base-v2

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/tmp TOKENIZERS_PARALLELISM=false

# torch w wersji CPU (z PyPI pociągnąłby kilka GB bibliotek CUDA), potem reszta zależności
COPY recommender/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
      "$(sed -n 's/^\(torch==[^ ]*\).*/\1/p' /tmp/requirements.txt)" \
 && pip install --no-cache-dir -r /tmp/requirements.txt "boto3==1.43.*"

# Model zapisany w obrazie: zimny start bez pobierania z Hugging Face. Wagi zapisują się z prawami 600,
# a Lambda uruchamia kod jako zwykły użytkownik - stąd chmod (inaczej "No such file" przy wczytywaniu)
RUN python -c "from sentence_transformers import SentenceTransformer as S; S('${EMBEDDING_MODEL_NAME}').save('/opt/model')" \
 && chmod -R a+rX /opt/model \
 && rm -rf /tmp/.cache
ENV EMBEDDING_MODEL=/opt/model HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TQDM_DISABLE=1

COPY recommender/ ${LAMBDA_TASK_ROOT}/recommender/
COPY src/recommender_api/*.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
