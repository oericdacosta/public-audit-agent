-- =============================================================================
-- ETL Schema Definition
-- All table definitions for the TCE data warehouse
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Tenders (Licitações)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS licitacoes (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    numero_licitacao TEXT,
    numero_processo TEXT,
    objeto_licitacao TEXT,
    modalidade_licitacao TEXT,
    data_realizacao_licitacao TEXT,
    valor_estimado DOUBLE,
    situacao_licitacao TEXT,
    exercicio_orcamento TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_lic_municipio ON licitacoes(municipio_id);
CREATE INDEX IF NOT EXISTS idx_lic_objeto ON licitacoes(objeto_licitacao);
CREATE INDEX IF NOT EXISTS idx_lic_mun_exerc ON licitacoes(municipio_id, exercicio_orcamento);


-- -----------------------------------------------------------------------------
-- Expenses (Despesas)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS despesas (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    exercicio_orcamento TEXT,
    mes_referencia TEXT,
    codigo_orgao TEXT,
    codigo_unidade_orcamentaria TEXT,
    codigo_funcao TEXT,
    codigo_subfuncao TEXT,
    codigo_programa TEXT,
    codigo_elemento_despesa TEXT,
    valor_empenhado DOUBLE,
    valor_liquidado DOUBLE,
    valor_pago DOUBLE,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_desp_municipio ON despesas(municipio_id);
CREATE INDEX IF NOT EXISTS idx_desp_mun_exerc ON despesas(municipio_id, exercicio_orcamento);


-- -----------------------------------------------------------------------------
-- Revenue (Receitas)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS receitas (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    exercicio_orcamento TEXT,
    mes_referencia TEXT,
    codigo_orgao TEXT,
    codigo_unidade_orcamentaria TEXT,
    codigo_receita TEXT,
    descricao_receita TEXT,
    valor_orcado DOUBLE,
    valor_arrecadado DOUBLE,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rec_municipio ON receitas(municipio_id);
CREATE INDEX IF NOT EXISTS idx_rec_mun_exerc ON receitas(municipio_id, exercicio_orcamento);


-- -----------------------------------------------------------------------------
-- Extra-Budgetary Expenses (Despesas Extra-Orçamentárias)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS balancete_despesa_extra (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    exercicio_orcamento TEXT,
    mes_referencia TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dextra_municipio ON balancete_despesa_extra(municipio_id);
CREATE INDEX IF NOT EXISTS idx_dextra_mun_exerc ON balancete_despesa_extra(municipio_id, exercicio_orcamento);


-- -----------------------------------------------------------------------------
-- Extra-Budgetary Revenue (Receitas Extra-Orçamentárias)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS balancete_receita_extra (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    exercicio_orcamento TEXT,
    mes_referencia TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rextra_mun_exerc ON balancete_receita_extra(municipio_id, exercicio_orcamento);


-- -----------------------------------------------------------------------------
-- Detailed Revenue (Talões de Receitas)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS taloes_receitas (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    exercicio_orcamento TEXT,
    codigo_municipio TEXT,
    codigo_orgao TEXT,
    codigo_unidade TEXT,
    codigo_rubrica TEXT,
    tipo_fonte TEXT,
    codigo_fonte TEXT,
    numero_talao_receita TEXT,
    data_talao_receita TIMESTAMP,
    data_referencia INTEGER,
    valor_receita DOUBLE,
    historico_receita TEXT,
    tipo_doc_contribuinte TEXT,
    numero_doc_contribuinte TEXT,
    nome_razao_social_contribuinte TEXT,
    numero_banco TEXT,
    numero_agencia_bancaria TEXT,
    numero_conta_corrente TEXT,
    numero_doc_credito TEXT,
    dt_credito_tr TIMESTAMP,
    tipo_doc_credito INTEGER,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trec_municipio ON taloes_receitas(municipio_id);
CREATE INDEX IF NOT EXISTS idx_trec_mun_exerc ON taloes_receitas(municipio_id, exercicio_orcamento);


-- -----------------------------------------------------------------------------
-- Detailed Extra Revenue (Talões Extras)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS taloes_extras (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    exercicio_orcamento TEXT,
    codigo_municipio INTEGER,
    codigo_orgao INTEGER,
    codigo_unidade TEXT,
    cd_conta_ctx INTEGER,
    nu_talao_receita_tx TEXT,
    dt_talao_receita_tx TIMESTAMP,
    dt_ref_tx INTEGER,
    vl_receita_tx DOUBLE,
    de_hist_receita_tx TEXT,
    tp_doc_contrib_tx TEXT,
    nu_doc_contrib_tx TEXT,
    nm_razao_social_contrib_tx TEXT,
    nu_banco_tx TEXT,
    nu_agencia_bancaria_tx TEXT,
    nu_conta_corrente_tx TEXT,
    nu_doc_credito_tx TEXT,
    dt_credito_tx TIMESTAMP,
    tp_doc_credito_tx INTEGER,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_textra_mun_exerc ON taloes_extras(municipio_id, exercicio_orcamento);


-- -----------------------------------------------------------------------------
-- Procurement Details (Contratos, Contratados, Licitantes, Itens)
-- -----------------------------------------------------------------------------

-- Contratos
CREATE TABLE IF NOT EXISTS contratos (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    numero_contrato TEXT,
    data_contrato DATE,
    data_inicio_vigencia DATE,
    data_fim_vigencia DATE,
    valor_total DOUBLE,
    descricao_objeto TEXT,
    tipo_contrato TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_contratos_mun ON contratos(municipio_id);

-- Contratados
CREATE TABLE IF NOT EXISTS contratados (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    numero_contrato TEXT,
    data_contrato DATE,
    documento_negociante TEXT,
    nome_negociante TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_contratados_mun ON contratados(municipio_id);

-- Licitantes (Participants)
CREATE TABLE IF NOT EXISTS licitantes (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    numero_licitacao TEXT,
    data_realizacao_licitacao DATE,
    documento_negociante TEXT,
    nome_negociante TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_licitantes_mun ON licitantes(municipio_id);

-- Itens Licitacoes
CREATE TABLE IF NOT EXISTS itens_licitacoes (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    numero_licitacao TEXT,
    data_realizacao_licitacao DATE,
    numero_sequencial_item INTEGER,
    descricao_item TEXT,
    valor_vencedor DOUBLE,
    quantidade TEXT,
    valor_unitario DOUBLE,
    nome_vencedor TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_itens_lic ON itens_licitacoes(municipio_id);


-- -----------------------------------------------------------------------------
-- ETL Metadata (Execution Tracking)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS etl_metadata (
    municipio_id TEXT,
    year INTEGER,
    source TEXT,
    status TEXT,
    record_count INTEGER,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (municipio_id, year, source)
);
-- -----------------------------------------------------------------------------
-- Fiscal Documents (Notas Fiscais, Pagamentos, Itens)
-- -----------------------------------------------------------------------------

-- Notas Fiscais
CREATE TABLE IF NOT EXISTS notas_fiscais (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    numero_nota_fiscal TEXT,
    data_emissao DATE,
    valor_liquido DOUBLE,
    valor_bruto DOUBLE,
    tipo_nota_fiscal TEXT,
    cpf_cnpj_credor TEXT,
    exercicio_orcamento TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_nf_mun_exerc ON notas_fiscais(municipio_id, exercicio_orcamento);
CREATE INDEX IF NOT EXISTS idx_nf_data ON notas_fiscais(data_emissao);

-- Notas Pagamentos
CREATE TABLE IF NOT EXISTS notas_pagamentos (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    numero_nota_pagamento TEXT,
    data_nota_pagamento DATE,
    valor_nota_pagamento DOUBLE,
    nome_pagador TEXT,
    exercicio_orcamento TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_np_mun_exerc ON notas_pagamentos(municipio_id, exercicio_orcamento);

-- Itens Notas Fiscais
CREATE TABLE IF NOT EXISTS itens_notas_fiscais (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    numero_nota_fiscal TEXT,
    descricao_item TEXT,
    quantidade DOUBLE,
    valor_unitario DOUBLE,
    valor_total DOUBLE,
    exercicio_orcamento TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_inf_mun_exerc ON itens_notas_fiscais(municipio_id, exercicio_orcamento);
CREATE INDEX IF NOT EXISTS idx_inf_descricao ON itens_notas_fiscais(descricao_item);

-- -----------------------------------------------------------------------------
-- Public Servants (Agentes Públicos)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agentes_publicos (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    cpf_servidor TEXT,  -- Masked for LGPD compliance
    nome_servidor TEXT,
    numero_matricula TEXT,
    cargo TEXT,
    tipo_cargo TEXT,
    situacao_funcional TEXT,
    codigo_vinculo TEXT,
    codigo_ingresso TEXT,
    valor_carga_horaria DOUBLE,
    exercicio_orcamento TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ap_mun_exerc ON agentes_publicos(municipio_id, exercicio_orcamento);
CREATE INDEX IF NOT EXISTS idx_ap_nome ON agentes_publicos(nome_servidor);
CREATE INDEX IF NOT EXISTS idx_ap_cargo ON agentes_publicos(cargo);

-- Liquidações (Settlement Confirmations)
CREATE TABLE IF NOT EXISTS liquidacoes (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    numero_empenho TEXT,
    data_liquidacao DATE,
    valor_liquidado DOUBLE,
    nome_responsavel_liquidacao TEXT,
    exercicio_orcamento TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_liq_mun_exerc ON liquidacoes(municipio_id, exercicio_orcamento);
CREATE INDEX IF NOT EXISTS idx_liq_empenho ON liquidacoes(numero_empenho);

-- Negociantes (Vendor Lookup)
CREATE TABLE IF NOT EXISTS negociantes (
    id TEXT PRIMARY KEY,
    numero_documento_negociante TEXT,  -- Masked for LGPD (if CPF)
    nome_negociante TEXT,
    endereco_negociante TEXT,  -- Masked for LGPD
    fone_negociante TEXT,  -- Masked for LGPD
    cep_negociante TEXT,  -- Masked for LGPD
    nome_municipio_negociante TEXT,
    uf_negociante TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_neg_nome ON negociantes(nome_negociante);
CREATE INDEX IF NOT EXISTS idx_neg_doc ON negociantes(numero_documento_negociante);

-- -----------------------------------------------------------------------------
-- Dimension / Lookup Tables
-- -----------------------------------------------------------------------------

-- Municípios
CREATE TABLE IF NOT EXISTS municipios (
    id TEXT PRIMARY KEY,
    codigo_municipio TEXT,
    nome_municipio TEXT,
    uf TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Funções
CREATE TABLE IF NOT EXISTS funcoes (
    id TEXT PRIMARY KEY,
    codigo_funcao TEXT,
    descricao_funcao TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Órgãos
CREATE TABLE IF NOT EXISTS orgaos (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    codigo_orgao TEXT,
    descricao_orgao TEXT,
    exercicio_orcamento TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_orgaos_mun ON orgaos(municipio_id);

-- Unidades Orçamentárias
CREATE TABLE IF NOT EXISTS unidades_orcamentarias (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    codigo_unidade_orcamentaria TEXT,
    descricao_unidade_orcamentaria TEXT,
    exercicio_orcamento TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_uo_mun ON unidades_orcamentarias(municipio_id);

-- Ordenadores
CREATE TABLE IF NOT EXISTS ordenadores (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    codigo_ordenador TEXT,
    nome_ordenador TEXT,
    exercicio_orcamento TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ord_mun ON ordenadores(municipio_id);

-- Contas Bancárias
CREATE TABLE IF NOT EXISTS contas_bancarias (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    numero_banco TEXT,
    numero_agencia TEXT,
    numero_conta TEXT,
    descricao_conta TEXT,
    exercicio_orcamento TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cb_mun ON contas_bancarias(municipio_id);

-- Programas
CREATE TABLE IF NOT EXISTS programas (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    codigo_programa TEXT,
    descricao_programa TEXT,
    exercicio_orcamento TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_prog_mun ON programas(municipio_id);

-- Orçamento Despesa (Projetos/Atividades)
CREATE TABLE IF NOT EXISTS orcamento_despesa (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    codigo_projeto_atividade TEXT,
    descricao_projeto_atividade TEXT,
    exercicio_orcamento TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_od_mun ON orcamento_despesa(municipio_id);

-- Orçamento Receita
CREATE TABLE IF NOT EXISTS orcamento_receita (
    id TEXT PRIMARY KEY,
    municipio_id TEXT,
    codigo_receita TEXT,
    descricao_receita TEXT,
    exercicio_orcamento TEXT,
    raw_data JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_or_mun ON orcamento_receita(municipio_id);
