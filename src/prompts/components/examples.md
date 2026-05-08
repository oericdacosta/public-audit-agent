# SECTION: DEFENSIVE CODING EXAMPLES

**PATTERN 1: SAFE KEY ACCESS**
*Use `.get()` with a default for safe key access on query results:*

```python
data = query_sql("SELECT SUM(valor_pago) as total FROM agg_despesas_por_funcao_ano")
# query_sql returns list[dict] on success
total = data[0].get('total', 0) if data else 0
print(total)
```

**PATTERN 2: PUSH-DOWN COMPUTATION**
*Problem:* Fetching all rows to sum in Python is slow and OOM-prone.
*Bad:*

```python
rows = query_sql("SELECT * FROM despesas") # 1M rows load
total = sum(r['val'] for r in rows)
```

*Good:*

```python
# Push aggregation to the DB engine
rows = query_sql("SELECT SUM(valor) as total FROM despesas")
total_val = rows[0]['total']
# NOTE: double braces needed for LangChain prompt escaping
print(f"Total: {{total_val}}")
```

**PATTERN 3: SAFE NULL AGGREGATION**
*Problem:* SUM() with NULL values returns NULL, not 0.
*Bad:*

```python
rows = query_sql("SELECT SUM(valor_pago) as total FROM despesas")
total = rows[0]['total']  # Pode ser None!
```

*Good:*

```python
rows = query_sql("SELECT COALESCE(SUM(valor_pago), 0) as total FROM despesas")
total = rows[0]['total']  # Sempre retorna número
```

**PATTERN 4: SAFE DATE RANGE**
*Problem:* BETWEEN is inclusive on both ends, which can cause off-by-one errors.
*Bad:* `WHERE data BETWEEN '2024-01-01' AND '2024-01-31'` (includes 31/01 at 00:00:00)
*Good:*

```python
# Use explicit bounds for date ranges
rows = query_sql("""
    SELECT * FROM licitacoes
    WHERE data_realizacao_licitacao >= '2024-01-01'
      AND data_realizacao_licitacao < '2024-02-01'
    LIMIT 10
""")
```
