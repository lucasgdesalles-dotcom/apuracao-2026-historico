#!/usr/bin/env python3
"""Gravador do histórico da apuração do 2º turno (25/10/2026).

Lê o resultado nacional de Presidente no TSE a cada 2 minutos e acrescenta um ponto em historico.json
sempre que o TSE publica um arquivo novo (hora de geração diferente). Cada ponto:
  {"dg": "25/10/2026", "hg": "17:32:10", "x": 12.34, "st": 61234,
   "c": {"22": [votos, % dos válidos], "13": [votos, % dos válidos]}}
O painel lê este arquivo para desenhar a evolução desde as 17h mesmo para quem abre a página depois.

Uso: python3 recorder.py [--ele 6258] [--out historico.json] [--minutes 58] [--every 120] [--no-push]
Para quando: o tempo acaba, ou o TSE marca a totalização como final (100% das seções), ou o arquivo já está final.
"""
import argparse, json, os, subprocess, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

BRT = timezone(timedelta(hours=-3))
URL = 'https://resultados.tse.jus.br/oficial/ele2026/{e}/dados/br/br-c0001-e{e:0>6}-u.json'
HERE = os.path.dirname(os.path.abspath(__file__))


def log(*a):
    print(datetime.now(BRT).strftime('%H:%M:%S'), *a, flush=True)


def git(*a, check=True):
    r = subprocess.run(['git', '-C', HERE, *a], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f'git {" ".join(a)}: {r.stderr.strip() or r.stdout.strip()}')
    return r


def num(s):
    try:
        return float(str(s).replace('.', '').replace(',', '.')) if ',' in str(s) else float(s)
    except (TypeError, ValueError):
        return 0.0


def fetch(ele):
    req = urllib.request.Request(URL.format(e=ele) + f'?t={int(time.time())}', headers={'User-Agent': 'apuracao-2026-historico', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def point(j):
    """Um ponto do histórico a partir do JSON nacional do TSE (None se ainda não há seções totalizadas)."""
    s = j.get('s') or {}
    st = int(num(s.get('st', 0)))
    if st <= 0:
        return None
    c = {}
    for carg in j.get('carg') or []:
        for agr in carg.get('agr') or []:
            for par in agr.get('par') or []:
                for cd in par.get('cand') or []:
                    c[str(cd.get('n'))] = [int(num(cd.get('vap', 0))), round(num(cd.get('pvap', '0')), 2)]
    return {'dg': j.get('dg', ''), 'hg': j.get('hg', ''), 'x': round(num(s.get('pst', '0')), 2), 'st': st,
            'ts': int(num(s.get('ts', 0))), 'c': c}


def load(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def merge(base, pts, ele, final):
    """Junta os pontos sem repetir (chave: data e hora de geração) e em ordem de seções apuradas."""
    by = {}
    for p in (base or {}).get('pts', []) + pts:
        if p and p.get('hg'):
            by[(p.get('dg'), p['hg'])] = p
    out = sorted(by.values(), key=lambda p: (p['x'], p['st'], p['dg'][6:] + p['dg'][3:5] + p['dg'][:2], p['hg']))
    return {'ele': str(ele), 'fonte': 'TSE, resultado nacional de Presidente (br-c0001), lido a cada 2 minutos',
            'final': bool(final or (base or {}).get('final')), 'atualizado': datetime.now(BRT).isoformat(timespec='seconds'),
            'pts': out}


def write(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, path)


def publish(path, mine, ele, final, push):
    """Grava e publica. Em conflito com outra gravação, recomeça do que está no GitHub e junta os pontos de novo."""
    name = os.path.relpath(path, HERE)
    for tent in range(6):
        if push:
            git('fetch', '-q', 'origin', 'main', check=False)
            git('reset', '-q', '--hard', 'origin/main', check=False)
        data = merge(load(path), mine, ele, final)
        write(path, data)
        if not push:
            return data
        git('add', name)
        if git('diff', '--cached', '--quiet', check=False).returncode == 0:
            return data
        last = data['pts'][-1] if data['pts'] else {}
        git('-c', 'user.name=Gravador da apuração', '-c', 'user.email=gravador@users.noreply.github.com',
            'commit', '-q', '-m', f"Apuração {ele}: {last.get('x', 0):.2f}% das seções (TSE {last.get('hg', '')})")
        r = git('push', '-q', 'origin', 'HEAD:main', check=False)
        if r.returncode == 0:
            return data
        log('push recusado, tentando de novo:', (r.stderr or '').strip()[:160])
        time.sleep(3 + 4 * tent)
    raise RuntimeError('não consegui publicar depois de 6 tentativas')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ele', default='6258')
    ap.add_argument('--out', default='historico.json')
    ap.add_argument('--minutes', type=float, default=58)
    ap.add_argument('--every', type=int, default=120)
    ap.add_argument('--no-push', action='store_true')
    a = ap.parse_args()
    path = os.path.join(HERE, a.out)
    push = not a.no_push
    if push:
        git('fetch', '-q', 'origin', 'main', check=False)
        git('reset', '-q', '--hard', 'origin/main', check=False)
    cur = load(path)
    if cur and cur.get('final') and str(cur.get('ele')) == str(a.ele):
        log('o histórico já está final; nada a fazer')
        return
    end = time.time() + a.minutes * 60
    mine, last_hg, errs = [], None, 0
    while True:
        final = False
        try:
            j = fetch(a.ele)
            errs = 0
            p = point(j)
            final = str(j.get('tf', '')).lower() == 's' and p is not None and p['x'] >= 100
            if p is None:
                log(f"TSE {j.get('dg')} {j.get('hg')}: nenhuma seção totalizada ainda")
            elif (p['dg'], p['hg']) != last_hg:
                last_hg = (p['dg'], p['hg'])
                mine.append(p)
                data = publish(path, mine, a.ele, final, push)
                lead = sorted(p['c'].items(), key=lambda kv: -kv[1][0])[:2]
                log(f"ponto {len(data['pts'])}: {p['x']:.2f}% ({p['st']} seções), TSE {p['hg']}", ' · '.join(f'{k} {v[1]:.2f}%' for k, v in lead))
            else:
                log(f"TSE ainda em {p['hg']}")
        except urllib.error.HTTPError as e:
            errs += 1
            log(f'TSE respondeu {e.code}')
        except Exception as e:  # rede, JSON parcial, git
            errs += 1
            log('erro:', repr(e)[:200])
        if final:
            log('totalização final; encerrando')
            return
        if time.time() + a.every > end:
            log('fim do tempo desta execução')
            return
        time.sleep(a.every)


if __name__ == '__main__':
    main()
