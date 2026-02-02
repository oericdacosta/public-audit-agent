# 🏛️ CivicAudit - Agente de Auditoria Pública

> **Sistema de Auditoria de Gastos Públicos com Inteligência Artificial para Municípios Brasileiros**

Um agente inteligente que analisa dados de gastos públicos usando LLMs, orquestração LangGraph e o Model Context Protocol (MCP).

[![CI](https://github.com/oericdacosta/public-audit-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/oericdacosta/public-audit-agent/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Coverage](https://img.shields.io/badge/coverage-30%25-yellow.svg)]()

---

## 📑 Índice

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Padrões MCP da Anthropic](#padrões-mcp-da-anthropic)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Instalação](#instalação)
- [Uso](#uso)
- [Testes](#testes)
- [Pipeline CI/CD](#pipeline-cicd)
- [Configuração](#configuração)

---

## Visão Geral

O CivicAudit é um sistema multi-agente que permite consultas em linguagem natural sobre dados de gastos públicos do Tribunal de Contas do Estado do Ceará (TCE-CE). Usuários podem fazer perguntas como:

- *"Qual foi o total gasto em educação em 2024?"*
- *"Compare gastos de saúde vs educação neste ano."*
- *"Liste as 10 maiores licitações por valor estimado."*

O sistema:

1. **Coleta** dados via ETL das APIs públicas do TCE-CE
2. **Armazena** em um banco de dados SQLite local
3. **Processa** perguntas em linguagem natural através de um workflow multi-agente
4. **Executa** SQL/Python gerado em sandboxes Docker isolados
5. **Retorna** respostas estruturadas e verificadas

---

## Arquitetura

### Workflow Multi-Agente (LangGraph)

O sistema usa **LangGraph** para orquestrar um grafo direcionado de agentes especializados:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         GRAFO DE WORKFLOW DE AUDITORIA                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [Pergunta do Usuário]                                                  │
│        │                                                                │
│        ▼                                                                │
│  ┌─────────────┐    UNSAFE    ┌─────────┐                              │
│  │  GUARDRAIL  │─────────────►│   FIM   │                              │
│  │  (Entrada)  │              └─────────┘                              │
│  └──────┬──────┘                                                        │
│         │ SAFE                                                          │
│         ▼                                                               │
│  ┌─────────────┐                                                        │
│  │  PLANEJADOR │  Decompõe pergunta em passos atômicos                 │
│  └──────┬──────┘                                                        │
│         │                                                               │
│         ▼                                                               │
│  ┌─────────────────────────────────────────────┐                       │
│  │       AGENTE FISCAL (Especialista SQL)       │                       │
│  │  ┌────────────┬─────────────┬────────────┐  │                       │
│  │  │list_tables │ get_schema  │generate_sql│  │                       │
│  │  └────────────┴──────┬──────┴────────────┘  │                       │
│  │                      │                       │                       │
│  │               ┌──────┴──────┐               │                       │
│  │               │  check_sql  │               │                       │
│  │               └─────────────┘               │                       │
│  └──────────────────────┬──────────────────────┘                       │
│                         │                                               │
│                         ▼                                               │
│  ┌─────────────────────────────────────────────┐                       │
│  │       AGENTE ANALISTA (Especialista Python)  │                       │
│  │  ┌──────────┐    ┌────────┐    ┌─────────┐  │                       │
│  │  │ generate ├───►│ critic ├───►│ execute │  │                       │
│  │  └────▲─────┘    └────┬───┘    └────┬────┘  │                       │
│  │       │               │              │       │                       │
│  │       └───── REJECT ──┘              │       │                       │
│  │       └─────── ERRO ─────────────────┘       │                       │
│  └──────────────────────┬──────────────────────┘                       │
│                         │                                               │
│                         ▼                                               │
│  ┌─────────────┐                                                        │
│  │  GUARDRAIL  │  Valida segurança da saída                            │
│  │   (Saída)   │                                                        │
│  └──────┬──────┘                                                        │
│         │                                                               │
│         ▼                                                               │
│    [Resposta]                                                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Descrição dos Agentes

| Agente | Função | Modelo |
|--------|--------|--------|
| **Guardrail** | Valida entrada/saída para segurança e adequação | `gpt-4o-mini` |
| **Planejador** | Decompõe perguntas complexas em passos atômicos | `gpt-4o` |
| **Fiscal** | Especialista SQL - gera e valida consultas ao banco | `gpt-4o` |
| **Analista** | Especialista Python - gera código de análise de dados | `gpt-4o` |
| **Crítico** | Revisa código gerado antes da execução | `gpt-4o-mini` |

### Estado Compartilhado (AgentState)

Todos os agentes se comunicam através de um dicionário de estado tipado:

```python
class AgentState(TypedDict, total=False):
    messages: List[BaseMessage]     # Histórico de conversa
    guardrail_verdict: str          # "SAFE" ou "UNSAFE"
    plan: str                       # Passos do Planejador
    sql_query: str                  # SQL do Agente Fiscal
    code: str                       # Código Python do Analista
    output: str                     # Resultado da execução
    error: str                      # Mensagens de erro
    evaluation: str                 # Veredicto do Crítico
    iterations: int                 # Contador de retentativas
```

---

## Padrões MCP da Anthropic

Este projeto implementa os padrões avançados de uso de ferramentas documentados pela Anthropic em seus artigos de engenharia:

### 1. Progressive Disclosure

**Problema:** Carregar todas as definições de ferramentas consome tokens excessivamente (~55K+ tokens para bibliotecas grandes).

**Solução Implementada:** O servidor MCP usa `defer_loading=True` para ferramentas pesadas e expõe uma ferramenta `search_tools` para descoberta sob demanda.

```python
# Em src/mcp/server.py

@register_tool(
    name="search_tools",
    description="Busca ferramentas disponíveis. Use para encontrar ferramentas diferidas.",
    defer_loading=False,  # Sempre visível
)
def search_tools(query: str) -> str:
    """Busca ferramentas por palavra-chave."""
    # Retorna apenas ferramentas que correspondem à busca

@register_tool(
    name="query_sql",
    defer_loading=True,  # Oculta até ser descoberta
)
def query_sql(sql_query: str) -> str:
    """Executa SQL - carregada sob demanda."""
```

**Benefício:** Apenas ferramentas essenciais são carregadas inicialmente (~500 tokens), preservando 95% da janela de contexto.

### 2. Context-Efficient Tool Results

**Problema:** Resultados intermediários de ferramentas consomem tokens desnecessários (ex: 10.000 linhas de dados).

**Solução Implementada:** O código é executado em um sandbox Docker que filtra e processa dados antes de retornar ao modelo.

```python
# O Analista gera código que filtra dados DENTRO do sandbox:
result = query_sql("SELECT * FROM despesas WHERE ano = 2024")
data = json.loads(result)

# Só retorna o resumo, não os dados brutos
total = sum(row['valor'] for row in data)
print(f"Total: R$ {total:,.2f}")  # Apenas isso entra no contexto
```

**Benefício:** O modelo vê apenas o resultado final (~1KB) em vez de dados brutos (~200KB).

### 3. Programmatic Tool Calling

**Problema:** Chamadas de ferramentas uma a uma geram muitos round-trips e latência.

**Solução Implementada:** O `shim.py` é injetado no container Docker e permite que o código gerado chame múltiplas ferramentas MCP via TCP em uma única execução.

```python
# Em src/execution/shim.py

def query_sql(sql_query: str) -> str:
    """Wrapper que chama o servidor MCP via JSON-RPC."""
    response = _rpc_call("tools/call", {
        "name": "query_sql",
        "arguments": {"sql_query": sql_query}
    })
    return response.get("result", {}).get("content", [{}])[0].get("text", "")
```

**Fluxo de Execução:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    PROGRAMMATIC TOOL CALLING                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────┐     Código Python     ┌─────────────────────┐  │
│  │  Analista  │ ───────────────────►  │   Docker Sandbox    │  │
│  │   (LLM)    │                       │                     │  │
│  └────────────┘                       │  ┌───────────────┐  │  │
│                                       │  │   shim.py     │  │  │
│                                       │  │  (injetado)   │  │  │
│                                       │  └───────┬───────┘  │  │
│                                       │          │          │  │
│                                       │   JSON-RPC/TCP      │  │
│                                       │          │          │  │
│                                       └──────────┼──────────┘  │
│                                                  │              │
│                                                  ▼              │
│                                       ┌─────────────────────┐  │
│                                       │    MCP Server       │  │
│                                       │   (tcp_server.py)   │  │
│                                       └──────────┬──────────┘  │
│                                                  │              │
│                                                  ▼              │
│                                       ┌─────────────────────┐  │
│                                       │      SQLite         │  │
│                                       │   civic_audit.db    │  │
│                                       └─────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Benefício:** O modelo escreve código que orquestra múltiplas operações, reduzindo round-trips e consumo de tokens em ~37%.

---

## Estrutura do Projeto

```
public-audit-agent/
├── .github/
│   └── workflows/
│       ├── ci.yml              # Pipeline principal de CI
│       └── pr-check.yml        # Validação de PR (título, tamanho)
├── data/
│   └── civic_audit.db          # Banco de dados SQLite
├── logs/                       # Logs da aplicação
├── src/
│   ├── agents/                 # Implementações dos agentes
│   │   ├── analyst.py          # Geração de código Python
│   │   ├── critic.py           # Revisão de código
│   │   ├── fiscal.py           # Geração de SQL
│   │   ├── guardrail.py        # Validação de segurança
│   │   └── planner.py          # Decomposição de perguntas
│   ├── etl/                    # Coleta de dados
│   │   ├── client.py           # Cliente da API TCE-CE
│   │   ├── db_manager.py       # Operações de banco
│   │   ├── main.py             # Orquestrador ETL
│   │   └── collectors/         # Coletores por domínio
│   │       ├── base.py         # Coletor abstrato
│   │       ├── despesas.py     # Coletor de despesas
│   │       ├── licitacoes.py   # Coletor de licitações
│   │       └── receitas.py     # Coletor de receitas
│   ├── execution/              # Execução de código
│   │   ├── sandbox.py          # Sandbox Docker
│   │   └── shim.py             # Cliente MCP para sandbox
│   ├── graph/                  # Workflow LangGraph
│   │   └── workflow.py         # Orquestrador principal
│   ├── mcp/                    # Model Context Protocol
│   │   ├── server.py           # Servidor MCP
│   │   └── tcp_server.py       # Transporte TCP
│   ├── prompts/                # Prompts dos agentes
│   ├── schemas/
│   │   └── state.py            # TypedDict AgentState
│   ├── tools/
│   │   └── sql.py              # Ferramentas SQL com segurança
│   └── utils/                  # Utilitários compartilhados
├── tests/
│   ├── conftest.py             # Fixtures do Pytest
│   ├── unit/                   # Testes unitários
│   └── integration/            # Testes de integração
├── config.yaml                 # Configuração da aplicação
├── Dockerfile                  # Definição do container
├── Makefile                    # Comandos de desenvolvimento
└── pyproject.toml              # Metadados do projeto
```

---

## Instalação

### Pré-requisitos

- Python 3.12+
- uv (Gerenciador de pacotes Python moderno)
- Docker (para execução do sandbox)

### Configuração

```bash
# Clonar repositório
git clone https://github.com/oericdacosta/public-audit-agent.git
cd public-audit-agent

# Instalar dependências com uv
uv sync --dev

# Copiar template de ambiente
cp .env.example .env
# Editar .env com suas API keys (OPENAI_API_KEY)

# Executar ETL para popular o banco
uv run python -m src.etl.main --year 2024
```

---

## Uso

### Executando o Servidor MCP

```bash
# Transporte STDIO (para Claude Desktop, etc.)
uv run python -m src.mcp.server

# Transporte TCP (para acesso via rede)
uv run python -m src.mcp.tcp_server --port 8000
```

### Executando o Workflow

```python
from src.graph.workflow import AuditGraph

graph = AuditGraph()
result = graph.run("Qual foi o total gasto em educação em 2024?")
print(result)
```

---

## Testes

### Executando Testes

```bash
# Executar todos os testes com cobertura
make test

# Executar todos os checks (lint, typecheck, test, security)
make check

# Executar apenas testes unitários
uv run pytest tests/unit/ -v

# Executar com relatório de cobertura
uv run pytest tests/ --cov=src --cov-report=term-missing
```

### Visão Geral da Suite de Testes

O projeto requer **mínimo de 30% de cobertura de código**. Veja o que cada módulo de teste valida:

#### `test_exceptions.py` (12 testes)

Testa classes de exceção customizadas.

| Teste | O que Valida |
|-------|-------------|
| `test_creates_error_with_message_only` | Exceção pode ser criada só com mensagem |
| `test_creates_error_with_message_and_details` | Formata "mensagem: detalhes" corretamente |
| `test_is_exception_subclass` | Todas herdam de `CivicAuditError` |
| `test_can_be_raised_and_caught` | Funcionam em blocos try/except |

**Como passar:** Garanta que todas as exceções herdam de `CivicAuditError` e implementam `__str__` corretamente.

---

#### `test_parsing.py` (7 testes)

Testa extração de blocos de código markdown.

| Teste | O que Valida |
|-------|-------------|
| `test_extracts_python_code_block` | Extrai código de blocos \`\`\`python |
| `test_extracts_code_block_without_language` | Trata blocos sem especificador de linguagem |
| `test_returns_plain_content_without_code_blocks` | Retorna texto bruto se não houver blocos |
| `test_handles_empty_content` | Retorna string vazia para entrada vazia |

**Como passar:** A função `clean_markdown_code()` deve analisar cercas de código markdown corretamente.

---

#### `test_sql_tools.py` (14 testes)

Testa validação de segurança e execução SQL.

| Teste | O que Valida |
|-------|-------------|
| `test_removes_single_line_comments` | Remove `-- comentários` |
| `test_removes_multi_line_comments` | Remove `/* comentários */` |
| `test_rejects_non_select_queries` | Bloqueia DELETE, UPDATE, etc. |
| `test_rejects_drop_keyword` | Bloqueia comandos DROP TABLE |
| `test_allows_valid_select` | Permite consultas SELECT seguras |
| `test_adds_limit_when_missing` | Adiciona LIMIT padrão |

**Como passar:** As ferramentas SQL devem implementar validação estrita:

- Permitir apenas `SELECT`
- Bloquear palavras-chave perigosas
- Sanitizar comentários
- Impor limites de resultado

---

#### `test_sandbox.py` (5 testes)

Testa sandbox Docker para execução segura de código.

| Teste | O que Valida |
|-------|-------------|
| `test_initializes_with_config_image` | Lê nome da imagem da config |
| `test_raises_config_error_for_missing_image` | Falha graciosamente sem config |
| `test_pulls_image_if_not_found` | Baixa imagem Docker automaticamente |
| `test_executes_code_in_container` | Executa Python em container isolado |
| `test_returns_error_on_container_error` | Captura erros do container corretamente |

**Como passar:** A classe `DockerSandbox` deve:

- Ler `sandbox.image` da config
- Criar containers efêmeros com limites de memória
- Retornar saída ou mensagens de erro formatadas

---

### Relatório de Cobertura

Cobertura atual por módulo:

| Módulo | Cobertura | Status |
|--------|-----------|--------|
| `exceptions.py` | 100% | ✅ |
| `parsing.py` | 100% | ✅ |
| `llm.py` | 100% | ✅ |
| `etl/client.py` | 100% | ✅ |
| `execution/sandbox.py` | 89% | ✅ |
| `tools/sql.py` | 71% | ✅ |
| `config.py` | 71% | ✅ |
| `agents/*.py` | 25-56% | ⚠️ |
| `etl/collectors/*.py` | 0% | ❌ |
| `mcp/*.py` | 0% | ❌ |

---

## Pipeline CI/CD

### Workflows

#### `ci.yml` - Pipeline Principal

| Job | Descrição |
|-----|-----------|
| **Lint & Format** | Executa `ruff check` e `ruff format` |
| **Type Check** | Executa `mypy` em modo estrito |
| **Tests** | Executa `pytest` com threshold de 30% de cobertura |
| **Security Scan** | Executa `pip-audit` + `bandit` SAST |

#### `pr-check.yml` - Validação de PR

| Check | Threshold |
|-------|-----------|
| **Título do PR** | Deve seguir [Conventional Commits](https://www.conventionalcommits.org/) |
| **Tamanho do PR** | ⚠️ Aviso > 300 linhas, ❌ Falha > 800 linhas |

### Formato de Mensagens de Commit

```
tipo: descrição

# Tipos:
# feat     - Nova funcionalidade
# fix      - Correção de bug
# docs     - Documentação
# style    - Formatação
# refactor - Reestruturação de código
# test     - Adição de testes
# chore    - Manutenção
# ci       - Mudanças no CI/CD
```

---

## Configuração

A configuração é gerenciada via `config.yaml`:

```yaml
# Modelos de IA
agent:
  analyst_model: "gpt-4o"      # Geração de código
  critic_model: "gpt-4o-mini"  # Revisão de código
  fiscal_model: "gpt-4o"       # Geração de SQL
  planner_model: "gpt-4o"      # Decomposição de perguntas
  max_retries: 3               # Tentativas máximas

# Fonte de Dados
audit:
  city_code: "162"             # Código do município
  data_retention_years: 10     # Anos para coletar

# Sandbox
sandbox:
  image: "python:3.12-slim"
  timeout: 30
  memory_limit: "512m"
```

### Variáveis de Ambiente

```bash
OPENAI_API_KEY=sk-...          # Obrigatório: Chave da API OpenAI
MCP_HOST=localhost             # Host do servidor MCP
MCP_PORT=8000                  # Porta do servidor MCP
```
