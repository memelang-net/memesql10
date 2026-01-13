import json, sys, re
from pathlib import Path
from glob import glob
from itertools import permutations
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memelang import Meme, MemePGSQL

groups = ('employees','invoices','movies','followers')

if __name__ == "__main__":
	stop = False
	for group in groups:
		if stop: stop = input('')
		joins = {}
		print(f"\n{group}")
		schema = open(f'./{group}/_schema.meme',encoding="utf-8").read()

		smeme=Meme(schema)

		# GET FOREIGN KEYS
		for_joins=['movie actor','title name']
		for meme in smeme:
			tabcols = []
			if meme[0].mode == '%for':
				for vec in meme: tabcols.append(str(vec[1]))
			for_joins.extend([' '.join(p) for p in permutations(tabcols, 2)])
		for_joins = set(for_joins)

		for file in glob(f'./{group}/ex*.meme'):
			if stop: stop = input('')
			print(file)
			with open(file, encoding='utf-8') as f: lines = [l.rstrip() for l in f]
			for i in range(len(lines) - 1):
				if lines[i].startswith('""" '):
					line = f'[{i}] {lines[i]}'

					# SYNTAX
					try:
						meme = MemePGSQL(lines[i + 1])
						memestr = str(meme).replace('; ',';').replace(' :last=','')
						sql = str(meme.select()[0])
						line+="\n"+memestr
					except Exception as e:
						print(line)
						print(e)
						exit()

					# JOIN
					pattern = r'\b(t\d+\.(\w+))\s*=\s*(t\d+\.(\w+))\b'
					for m in re.finditer(pattern, sql):
						join = f'{m.group(2)} {m.group(4)}'
						if m.group(2)==m.group(4): continue
						if join in for_joins: continue
						print(line)
						print(f'WARN_JOIN: {join}\n')
						stop = True

					# ;_;x y @
					pattern = r';_;[\w\s]+@'
					if re.search(pattern, memestr):
						print(line)
						print(f'WARN_SAME\n')
						stop = True

					# REDUNDANT COL
					pattern = r'(?=(?:[^"]*"[^"]*")*[^"]*$)\b([a-z_]+)\s+[^@]+\b\1\b;'
					for mtch in re.findall(pattern, memestr):
						if any(s in mtch for s in ('%m','"')): continue
						print(line)
						print(f'WARN_COL: {mtch}\n')
						stop = True

					# REDUNDANT TABLE
					if False and '@ @ @' not in memestr:
						pattern = r'\b(\w+)\s+[^\s;]+\s+[^\s;]+;.+?;\1\s+[^\s;]+\s+[^\s;]+'
						for mtch in re.findall(pattern, memestr):
							if any(s in mtch for s in ('%m','"')): continue
							print(line)
							print(f'WARN_TAB: {mtch}\n')
							stop = True

					# :FUNC>=X;(MISSING_FUNC)<=Y
					pattern = r'[\w\:]*\:(?:min|max|cnt|sum|avg)[\w\:]*[<>=]+[\d\.\-]+;[<>=]+[\d\.\-]+'
					if re.search(pattern, memestr):
						print(line)
						print(f'WARN_XFUNC\n')
						stop = True

					# BROKEN COMPARE >=X;...;<=Y
					pattern = r'\D;[<>=]'
					if re.search(pattern, memestr):
						print(line)
						print(f'WARN_CMP\n')
						stop = True
