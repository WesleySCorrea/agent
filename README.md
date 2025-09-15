# 🛰️ Agent

O **Agent** é um serviço em **Python** que consome mensagens de uma fila no **RabbitMQ** e executa comandos recebidos.  
Ele atua como um executor remoto, respondendo a instruções enviadas pelo backend.

---

## 🚀 Funcionalidades

- Conexão automática ao RabbitMQ.
- Escuta contínua de mensagens em uma fila definida.
- Execução de comandos recebidos via fila.
- Configuração simples através de variáveis de ambiente.

---

## ⚙️ Instalação

### 1. Garantir que o Python 3 esteja instalado
Verifique sua versão:

```bash
python3 --version
```

#### Se não tiver instalado:

* **Ubuntu/Debian**
```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv
```

* **Fedora/CentOS**
```bash
sudo dnf install -y python3 python3-pip
```

* **Windows**
Baixe o instalador oficial em: python.org/downloads

### 2. Clonar o repositório

```bash
git clone https://github.com/WesleySCorrea/agent.git

cd agent
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. ▶️ Executando o Agent

#### 4.1 Antes de rodar, configure as variáveis de ambiente em um arquivo `.env` na raiz do projeto.  

| Variável        | Valor/Exemplo                              | Descrição                                                   |
|-----------------|--------------------------------------------|-------------------------------------------------------------|
| `RABBITMQ_URL`  | `amqp://guest:guest@localhost:5672/`       | URL de conexão com o RabbitMQ (inclui usuário, senha e host) |
| `QUEUE_NAME`    | `agent-commands`                           | Nome da fila que o agente irá escutar                       |
| `BASE_PATH`     | `/tmp/agent`                               | Diretório base onde os comandos serão executados/arquivos salvos |

Exemplo de `.env`:

#### 4.2 Depois, execute:

```bash
python agent.py
```

#### 4.3 Se tudo estiver certo, você verá algo como:
```text
[agent] ===== CONFIG ATIVA =====
[agent] RABBITMQ_URL = amqp://guest:guest@localhost:5672/
[agent] QUEUE_NAME   = agent-commands
[agent] BASE_PATH    = /tmp/agent
[agent] ========================

[agent] conectando ao RabbitMQ... tent 1/10
[agent] ouvindo fila 'agent-commands' RABBITMQ_URL=amqp://guest:guest@localhost:5672/
[agente rodando e funcionando]
```