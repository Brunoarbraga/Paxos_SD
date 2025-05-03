# Usar a imagem base do Ubuntu
FROM ubuntu:latest

# Atualizar pacotes e instalar o Python
RUN apt-get update && \
    apt-get install -y python3 python3-pip
    RUN pip install --break-system-packages pymongo

    RUN apt-get update && apt-get install -y ca-certificates && update-ca-certificates
# Definir o diretório de trabalho
WORKDIR /src

ENV PYTHONPATH=/src

# Copiar os arquivos no.py, client.py e constants.py para o container
COPY ./src /src/
