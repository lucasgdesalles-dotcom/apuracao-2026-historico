# Histórico da apuração 2026

Arquivos gravados durante a apuração do 2º turno (25/10/2026), lidos do TSE a cada 2 minutos, para o gráfico de evolução do painel.

- `historico.json`: um ponto por arquivo novo do TSE (resultado nacional de Presidente), desde as 17h.
  Cada ponto tem a data e a hora de geração do TSE (`dg`, `hg`), o % de seções totalizadas (`x`), as seções (`st`, `ts`)
  e, por número de candidato, `[votos, % dos votos válidos]` (`c`).
- `recorder.py`: o gravador. Roda em execuções agendadas de cerca de uma hora cada, no domingo, das 16h55 até a totalização final.

Fonte: https://resultados.tse.jus.br (dados públicos do TSE).
