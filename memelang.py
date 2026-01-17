'''
info@memelang.net | (c)2026 HOLTWORK LLC | Patents Pending
This script parses MEMELANG, a terse query DSL with axial grammar
Grid(Axis2) -> Axis1 -> Axis0 -> Cell
Whitespaces are syntactic and trigger "new Cell"
Never space between operator/comparator/comma/flag and values
'''

MEMELANG_VER = 10.10

syntax = '[table WS] [column WS] ["<=>" "\"" string "\""] [":" "$" var][":" ("min"|"max"|"cnt"|"sum"|"avg"|"last"|"grp")][":" ("asc"|"des")] [("="|"!="|">"|"<"|">="|"<="|"~"|"!~") (string|int|float|("$" var)|"@"|"_")] ";"'

examples = '''
% mode tab;
roles id :TYP=INT;>0;rating :DESC="Decimal 0-5 star rating of performance";:TYP=DEC;>0;<=5;actor :DESC="Actor's full name";:TYP=STR;movie :DESC="Movie's full name";:TYP=STR;character :DESC="Character's full name";:TYP=STR;;
actors id :TYP=INT;>0;name :DESC="Actor's full name";:TYP=STR;age :DESC="Actor's age in years";:TYP=INT;>=0;<200;;
movies id :TYP=INT;>0;description :DESC="Brief description of movie plot";:TYP=STR;year :DESC="Year of production AD";:TYP=INT;>1800;<2100;genre scifi,drama,comedy,documentary;:TYP=STR;title :DESC="Full movie title";:TYP=STR;;
actors name _;roles actor @;;
movies title _;roles movie @;;
roles id :grp:cnt=1;;
roles movie :grp;actor :grp;character :grp:cnt=1;;
actors id :grp:cnt=1;;
movies id :grp:cnt=1;;

% mode qry;
""" All movies """
movies _ _;;

""" Every role """
roles _ _;;

""" Titles and descriptions for movies """
movies title _;description _;;

""" Actor name and ages """
actors name _;age _;;

""" Actors age 41 years or older """
actors age >=41;_;;

""" Role 567 and 8901 """
roles id 567,8901;_;;

""" Films with dystopian society narratives sim>.33 """
movies description <=>"dystopian"<0.33;_;;

""" Movies titled with Star released in 1977 or 1980 """
movies title ~"Star";year 1977,1980;_;;

""" Actors named like Ana aged 20 to 35 inclusive """
actors name ~"Ana";age >=20;<=35;_;;

""" Roles rated below 1.5 for movies before 1980 """
movies year <1980;title _;roles movie @;rating <1.5;_;;

""" Roles sort rating descending, movie descending """
roles rating :des;movie :des;;

""" All movies before 1970 ordered by year ascending """
movies year :asc<1970;_;;

""" Average performer rating at least 4.2 """
roles rating :avg>=4.2;actor :grp;;

""" Minimum role rating by actor, low to high """
roles rating :min:asc;actor :grp;;

""" Roles in movies mentioning robot rated 3+ """
movies description <=>"robot"<=$sim;title _;roles movie @;rating >=3;;

""" Costars seen with Bruce Willis and Uma Thurman """
roles actor :$a~"Bruce Willis","Uma Thurman";movie _;@ @ @;actor !$a;;

""" War stories before 1980: top 12 movies by minimum role rating """
movies year <1980;description <=>"war"<=$sim;title :grp;roles movie @;rating :min:des;% beg 0;% lim 12;;

""" Roles for movies Hero or House of Flying Daggers where actor name includes Li, actor A-Z """
movies title "Hero","House of Flying Daggers";roles movie @;actor :asc~"Li";;
'''

import re, sys, json
from typing import Optional, Union, List, Iterator, Pattern
Err = SyntaxError


### SYNTAX ###

CELL_PATTERN = (
	('DAT_QUO',   r'"(?:[^"\\\n\r]|\\.)*"'),
	('DAT_EMB',	r'\[(?:-?\d+(?:\.\d+)?)(?:\s*,\s*-?\d+(?:\.\d+)?)*\]'),
	('MOD_L2',	 r'<->'),
	('MOD_COS',	 r'<=>'),
	('MOD_IP',	 r'<#>'),
	('CMP_GE',	 r'>='),
	('CMP_LE',	 r'<='),
	('CMP_DSIM', r'!~'),
	('CMP_NOT',	 r'!=?'), # a!=b or a!b
	('CMP_EQL',	r'='),
	('CMP_GT',	r'>'),
	('CMP_LT',	r'<'),
	('CMP_SIM', r'~'),
	('BIND',	r':\$\w+'),
	('FLAG',	r':[a-zA-Z]+'),
	('DAT_VAR',	r'\$\w+'),
	('DAT_WLD', r'_'),
	('DAT_MS',  r'\^'),
	('DAT_AT',  r'@'),
	('DAT_MET', r'%'),
	('DAT_TS',  r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'),
	('DAT_YMD',	r'\d{4}-\d{2}-\d{2}'),
	('DAT_DEC',	r'-?\d*\.\d+'),
	('DAT_INT',	r'-?\d+'),
	('DAT_ID',  r'[A-Za-z][A-Za-z0-9_]*'),
	('OR',	 r','),
	('WS',	 r'\s+'),
	('MISMATCH', r'.'),
)

CELL_REGEX=re.compile("|".join(f"(?P<{k}>{p})" for k, p in CELL_PATTERN))

# Atomic token
class Tok:
	def __init__(self, kind: str, lex: str):
		self.kind = kind
		self.lex = lex
		if   kind == 'DAT_QUO': self.dat = json.loads(lex)
		elif kind == 'DAT_EMB': self.dat = json.loads(lex)
		elif kind == 'DAT_DEC': self.dat = float(lex)
		elif kind == 'DAT_INT': self.dat = int(lex)
		else: self.dat = lex
	def __str__(self): return self.lex
	def __repr__(self): return self.lex


TOK_NULL = Tok('NULL', '')
TOK_EQL_ELIDE = Tok('CMP_EQL', '')  # default, elided '='


# Sequence of tokens
class Seq(list[Tok]):
	opr: Tok = TOK_NULL
	def __init__(self, *items):
		super().__init__(items)
		self.opr = TOK_NULL
	def __str__(self): return self.opr.lex.join(map(str, self))


# Predicate expression
class Cell:
	left: Seq
	flag: Seq
	comp: Tok
	right: Seq

	def __init__(self, src: str):
		self.left = Seq()
		self.flag = Seq()
		self.comp = TOK_EQL_ELIDE
		self.right = Seq()

		toks = []
		for m in CELL_REGEX.finditer(src):
			kind = m.lastgroup
			text = m.group()
			if kind == 'WS': continue
			if kind == 'MISMATCH': raise Err(f'E_TOK {text!r}')
			toks.append(Tok(kind, text))

		i, n = 0, len(toks)

		def peek(): return toks[i].kind if i < n else ''

		def take():
			nonlocal i
			if i >= n: raise Err('E_EOF')
			t = toks[i]
			i += 1
			return t

		# LEFT (prefix MOD)
		if peek().startswith('MOD'):
			self.left.opr = take()
			self.left.append(TOK_NULL)
			t = take()
			if not t.kind.startswith('DAT'): raise Err('E_TERM_DAT')
			self.left.append(t)

		# FLAGS
		while peek() in {'FLAG','BIND'}:
			self.flag.append(take())

		# COMPARATOR
		if peek().startswith('CMP'):
			self.comp = take()
			if not peek().startswith('DAT'): raise Err('E_CMP_DAT')

		# RIGHT (values, OR-joined)
		while peek().startswith('DAT'):
			self.right.append(take())
			if peek() == 'OR':
				self.right.opr = take()
				if not peek().startswith('DAT'): raise Err('E_OR_TRAIL')

		if i != n: raise Err(f'E_EXPR_TRAIL {toks[i:]}')

	# PLACEHOLDER: OVERWRITE WITH YOUR EMBEDDING FUNCTION
	def vectorize(self, tok: Tok) -> Tok:
		if tok.kind == 'DAT_EMB': return tok
		if tok.kind not in {'DAT_QUO', 'DAT_ID'}: raise Err('E_EMBED')
		return Tok('DAT_EMB', json.dumps([0.1, 0.2]))

	@property
	def single(self) -> Tok:
		return (
			self.right[0]
			if self.comp.kind == 'CMP_EQL' and len(self.right) == 1
			else TOK_NULL
		)

	def __str__(self) -> str: return f"{self.left}{self.flag}{self.comp.lex}{self.right}"

	def __repr__(self) -> str: return str(self)


### GRAMMAR ###

class Axis(list):
	sep: str = None			# SEPERATOR TOKEN
	sepreg: str = None		# SEPERATOR REG EXP
	sepstr: str = None		# SEPERATOR OUT
	minlen: int = 0			# FIXED LENGTH (0=No)
	empt: bool = False		# ALLOW EMPTY SUB-AXES?
	sub = None				# SUB-AXIS NAME

	def __init__(self, src: str):
		if self.sep is None: raise Err('E_AXIS_SEP')
		if not self.sepreg: self.sepreg = re.escape(self.sep)
		if not self.sepstr: self.sepstr = self.sep + ' '
		self.parse(src.strip())

	@property
	def regex(self) -> Pattern[str]:
		return re.compile(rf'''
		(?P<COMM>"""(?:(?!""")[^\n\r\\]|\\.)*""")|
		(?P<EXPQ>"(?:[^"\\\n\r]|\\.)*")|
		(?P<SEP>{self.sepreg})|
		(?P<EXPM>[^"{re.escape(self.sep[0])}]+)|
		(?P<EXPS>.)
		''', re.VERBOSE)

	def parse(self, src: str):
		exprs: List[str] = []

		for m in self.regex.finditer(src):
			# build expression
			if m.lastgroup in {"EXPQ", "EXPM", "EXPS"}: exprs.append(m.group())
			# append sub-axis
			elif m.lastgroup == "SEP" and (exprs or self.empt):
				self.append(self.sub("".join(exprs)))
				exprs.clear()

		# debuffer expression
		if exprs: self.append(self.sub("".join(exprs)))

		# rectangularization
		if self.minlen: self[:0] = [self.sub('') for _ in range(self.minlen-len(self))]

	def __str__(self) -> str:
		items = [str(t) for t in self]
		return self.sepstr.join([s for s in items if (s or self.empt)])


# "Table column value" semantic sequence of Cell predicates
class Axis0(Axis):
	sep = ' '
	sepstr = ' '
	sepreg = r'\s+'
	minlen = 3
	sub = Cell

# AND-joined sequence of Axis0
class Axis1(Axis):
	sep = ';'
	sub = Axis0

# OR-joined sequence of Axis1
class Axis2(Axis):
	sep = ';;'
	sub = Axis1


### PG SQL ###

PH = '%s'

class SQL:
	lex: str
	param: List[Union[int, float, str, list]]
	def __init__(self, lex: str = '', param: Optional[List[Union[int, float, str, list]]] = None):
		self.lex = lex
		self.param = [] if param is None else param

	def __str__(self) -> str:
		lex = self.lex
		for p in self.param: lex = lex.replace(PH, json.dumps(p), 1)
		return lex

	def __repr__(self) -> str: return str(self)


class Alias(str):
	pass


class Grid(Axis2):

	def select(self) -> List[SQL]:

		sql: List[SQL] = []
		TAB, COL, VAL = 0, 1, 2
		flag2sql = {':cnt':'COUNT',':sum': 'SUM', ':avg': 'AVG', ':min': 'MIN', ':max': 'MAX', ':last': 'MAX'}
		cmp2sql = {'EQL':'=','NOT':'!=','GT':'>','GE':'>=','LT':'<','LE':'<=','SIM':'ILIKE','DSIM':'NOT ILIKE'}
		mod2sql = {'MOD_COS': '<=>','MOD_L2': '<->','MOD_IP': '<#>'}
		bind = {'lim':0,'beg':0,'sim':0.5,'mode':'qry'}

		def deref(cell: Cell) -> Iterator[SQL]:
			for t in cell.right:
				if t.kind == 'DAT_VAR': key=t.lex[1:]
				elif t.kind == 'DAT_AT': key='@'
				else: key=None
				if key:
					if key not in bind: raise Err(f'E_VAR_BIND {key}')
					val = bind[key]
				else: val = t.dat

				yield SQL(val) if isinstance(val, Alias) else SQL(PH, [val])

		for axis1 in self:
			mem = [{'val':None,'alias':None,'cnt':-1} for _ in range(3)]
			query = {'select':[],'from':[],'groupby':[],'where':[],'having':[],'orderby':[]}
			GROUPED = False
			ALLSELECTED = False

			for axis0 in axis1:

				axis0str = [str(cell.single.dat) for cell in axis0]

				if axis0str[TAB]=='%':
					bind[axis0str[COL]]=axis0[VAL].single.dat
					if bind[axis0str[COL]] == '': raise Err('E_MET_VAL')
					continue
				if bind['mode']!='qry': continue

				if axis0str == ['','','_']:
					ALLSELECTED=True
					continue

				# TABLE
				if axis0str[TAB]=='':
					if mem[TAB]['alias'] is None: raise Err('E_TAB_REQ')
				else:
					tkind = axis0[TAB].single.kind
					if tkind == 'NULL': raise Err('E_TAB_NON')
					# @ means self-join
					elif tkind == 'DAT_AT':
						if mem[TAB]['val'] is None: raise Err('E_TAB_SAME')
						mem[TAB]['cnt']+=1
						mem[TAB]['alias']=Alias(f"t{mem[TAB]['cnt']}")
					# named table
					else:
						if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_$]{0,62}', axis0str[TAB]): raise Err('E_TAB_CHR')
						mem[TAB]['cnt']+=1					
						mem[TAB]['alias']=Alias(f"t{mem[TAB]['cnt']}")
						mem[TAB]['val']=axis0str[TAB]
					query['from'].append(SQL(f"{mem[TAB]['val']} AS {mem[TAB]['alias']}"))

	
				# COLUMN
				# select all
				if axis0str[COL] == '_':
					ALLSELECTED=True
					continue
				# update column alias with new table alias on self-join
				elif axis0str[COL] in ('','@'):
					if mem[COL]['val'] is None: raise Err('E_COL_NON')
					mem[COL]['alias']=Alias(f"{mem[TAB]['alias']}.{mem[COL]['val']}")
				# named column
				else:
					mem[COL]['cnt']+=1
					if axis0[COL].single.kind != 'NULL':
						if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_$]{0,62}', axis0str[COL]): raise Err('E_COL_CHR')
						mem[COL]['alias']=Alias(f"{mem[TAB]['alias']}.{axis0str[COL]}")
						mem[COL]['val']=axis0str[COL]

				# VALUE
				mem[VAL]['alias']=mem[COL]['alias']
				mem[VAL]['val']=mem[COL]['alias']

				# MOD
				if axis0[VAL].left.opr.kind in mod2sql:
					v = axis0[VAL].vectorize(axis0[VAL].left[1])
					mem[VAL]['alias'] = Alias(f"({mem[VAL]['alias']}{mod2sql[axis0[VAL].left.opr.kind]}'{v.lex}'::VECTOR)")

				flags = [str(f) for f in axis0[VAL].flag]
				agged = False

				# aggregate
				for flag,agg in flag2sql.items():
					if flag in flags:
						#if agged: raise Err('E_AGG_AGG')
						mem[VAL]['alias']=Alias(f"{agg}({mem[VAL]['alias']})")
						agged=True

				# group by
				if ':grp' in flags:
					if agged: raise Err('E_GRP_AGG')
					GROUPED = True
					query['groupby'].append(SQL(mem[COL]['alias']))

				# sort
				if ':asc' in flags: query['orderby'].append(SQL(mem[VAL]['alias']))
				elif ':des' in flags: query['orderby'].append(SQL(mem[VAL]['alias']+' DESC'))

				# select
				sel=SQL(mem[VAL]['alias'])
				if not query['select'] or query['select'][-1].lex!=sel.lex:
					query['select'].append(sel)

				# where/having
				if axis0[VAL].right and axis0[VAL].single.lex!='_':
					rights = list(deref(axis0[VAL]))
					wparams = [p for r in rights for p in r.param]
					commas = ','.join([r.lex for r in rights])

					hw = 'having' if agged else 'where'

					compkind = axis0[VAL].comp.kind[4:]
					
					if len(rights)==1 and compkind not in {'SIM', 'DSIM'}: query[hw].append(SQL(f"{mem[VAL]['alias']} {cmp2sql[compkind]} {commas}", wparams))
					else:
						if compkind=='EQL':    query[hw].append(SQL(f"{mem[VAL]['alias']} IN ({commas})", wparams))
						elif compkind=='NOT':  query[hw].append(SQL(f"{mem[VAL]['alias']} NOT IN ({commas})", wparams))
						elif compkind=='SIM':  query[hw].append(SQL('('+" OR ".join([f"{mem[VAL]['alias']} ILIKE CONCAT('%', %s, '%')" for _ in rights])+')',wparams))
						elif compkind=='DSIM': query[hw].append(SQL('('+" AND ".join([f"{mem[VAL]['alias']} NOT ILIKE CONCAT('%', %s, '%')" for _ in rights])+')',wparams))
						else: raise Err('E_COMP_OR')

				# bind
				bind['@']=Alias(mem[VAL]['alias'])
				for flag in axis0[VAL].flag:
					if flag.kind=='BIND': bind[flag.lex[2:]]=Alias(mem[VAL]['alias'])

			if ALLSELECTED:
				query['select']=[]
				for f in query['from']:
					m = re.search(r"\bAS\s+(t\d+)\b", f.lex)
					query['select'].append(SQL(f"{m.group(1)}.*"))
			elif GROUPED:
				groupstrs=[s.lex for s in query['groupby']]
				for s in query['select']:
					if '(' not in s.lex[1:] and s.lex not in groupstrs: s.lex=f"MAX({s.lex})"

			if not query['from']:
				sql.append(SQL(''))
				continue

			SQLPARTS=[
				['SELECT', ', ', 'select'],
				['FROM', ', ', 'from'],
				['WHERE', ' AND ', 'where'],
				['GROUP BY', ', ', 'groupby'],
				['HAVING', ' AND ', 'having'],
				['ORDER BY', ', ', 'orderby'],
			]

			sqlstr,params='',[]
			for keyword, sep, ikey in SQLPARTS:
				if not query[ikey]: continue
				sqlstr+=' '+keyword+' '+sep.join([s.lex for s in query[ikey]])
				for s in query[ikey]: params.extend(s.param)

			if bind['lim']: sqlstr += f" LIMIT {int(bind['lim'])}"
			if bind['beg']: sqlstr += f" OFFSET {int(bind['beg'])}"

			sql.append(SQL(sqlstr[1:], params))
		return sql


### CLI ###

if __name__ == "__main__":
	if len(sys.argv)>1: lines=[' '.join(sys.argv[1:])]
	else: lines = examples.splitlines()
	if lines:
		for i in range(len(lines)):
			if lines[i].startswith('"""'):
				print(f'{lines[i]}')
				grid=Grid(lines[i+1])
				sel = grid.select()
				print(str(grid))
				if sel: print(str(sel[0]))
				print()