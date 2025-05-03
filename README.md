# Paxos Distributed System

Esse projeto é uma solução distribuída para o protocolo de consenso Paxos, utilizando docker-compose.

## Paxos

Paxos é um protocolo de consenso utilizado para garantir confiabilidade entre elementos de um cluster,
onde podem haver falhas ou sabotagens em algum elemento.

O protocolo divide os elementos do cluster em 3 funções: Proposers, acceptors e leaners.

<img src="images/paxos_protocol.png" width="300">
veja: https://en-m-wikipedia-org.translate.goog/wiki/Paxos_(computer_science)?_x_tr_sl=en&_x_tr_tl=pt&_x_tr_hl=pt&_x_tr_pto=tc

Em suma:
- Proposers recebem requisições dos clientes e repassam-as para os acceptors com IDs de transação únicos
- Accepters, caso todos aceitem o mesmo ID de transação, repassam a requisição para os leaners
- Leaners realizam o consenso, aprendem o valor de transação, e realizam o commit no recurso R

## Tolerância à falha e Cluster Store

Para adicionar um nível de tolerância a falha sobre o protocolo Paxos, é adicionado o Cluster Store.

O cluster Store é um cluster de réplicas, onde todos os elementos possuem uma cópia local do recurso R,
porém, apenas o elemento considerado "primário" possui permissão de escrita no recurso R original.

<img src="images/cluster_store.png" width="300">


Para cada elemento falho do cluster store, há uma substituição ou corte na comunicação:


<img src="images/fault_tolerance_1.png" width="300">
<img src="images/fault_tolerance_2.png" width="300">
<img src="images/fault_tolerance_3.png" width="300">


## Overview
<img src="images/project_overview.png" width="300">

## Executando o projeto
Veja instruções.txt

