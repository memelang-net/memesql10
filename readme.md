### About

Memelang is a token-optimized query language that significantly reduces token count and model size for LLM RAG. The pipeline is:
1. LLM emits low-token Memelang queries
2. **memelang.py** expands Memelang to SQL
3. Database executes SQL query

The **/train/** folder contains example natural language to Memelang conversions for LLM training.


### Example

This 22-token Memelang query:

```memelang 
roles actor :$a="Mark Hamill"; movie *;@ @ @; actor !$a
```

is expanded into a 50 token SQL query:

```sql
SELECT t0.actor, t0.movie, t1.movie, t1.actor FROM roles AS t0, roles AS t1 WHERE t0.actor = 'Mark Hamill' AND t1.id != t0.id AND t1.movie = t0.movie
```

### Links

* Video: https://www.youtube.com/watch?v=25tJzR5pEd0
* Paper: https://arxiv.org/abs/2512.17967
* Patent Spec: https://patents.google.com/patent/US20250068615A1
* Contact: info@memelang.net

### Legal

©2026 HOLTWORK LLC. US Patent 12,475,098 and additional pending. This software is free to use for development, testing, and educational purposes. Commercial deployment, redistribution, or production use requires a separate license.