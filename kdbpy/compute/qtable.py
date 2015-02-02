from collections import OrderedDict
from kdbpy import KQ
from datashape import Record, var, bool_, int8, int16, int32, int64
from datashape import float32, float64, string, date_, datetime_
from datashape import TimeDelta, null, DataShape
from blaze import Symbol, discover, Expr, compute
from kdbpy.util import PrettyMixin
from kdbpy import q


qtypes = {'b': bool_,
          'x': int8,
          'h': int16,
          'i': int32,
          'j': int64,
          'e': float32,
          'f': float64,
          'c': string,  # q char
          's': string,  # q symbol
          'm': date_,  # q month
          'd': date_,
          'z': datetime_,
          'p': datetime_,  # q timestamp
          'u': TimeDelta(unit='m'),  # q minute
          'v': TimeDelta(unit='s'),  # q second
          'n': TimeDelta(unit='ns'),  # q timespan
          't': TimeDelta(unit='ms'),
          '': null}


class Tables(PrettyMixin, OrderedDict):
    def __init__(self, *args, **kwargs):
        super(Tables, self).__init__(*args, **kwargs)

    def _repr_pretty_(self, p, cycle):
        assert not cycle, 'cycles not allowed'
        with p.group(4, '%s({' % type(self).__name__, '})'):
            for idx, (k, v) in enumerate(self.items()):
                if idx:
                    p.text(',')
                    p.breakable()
                p.pretty(k)
                p.text(': ')
                p.pretty(v)


def tables(kdb):
    names = kdb.tables.name
    metadata = kdb.eval(r'meta each value "\\a"')

    # t is the type column of the result of "meta `t" in q
    syms = []
    for name, meta in zip(names, metadata):
        types = [qtypes[t.lower()] for t in meta.t.fillna('')]
        columns = meta.index
        ds = var * Record(list(zip(columns, types)))
        syms.append((name, Symbol(name, ds)))
    return Tables(syms)


def qp(t):
    if isinstance(t, Expr):
        t = compute(t)
    t = getattr(t, 'data', t)
    return t.engine.eval('.Q.qp[%s]' % t.tablename).item()


def is_partitioned(t):
    return qp(t) is True


def is_splayed(t):
    return qp(t) is False


def is_standard(t):
    return int(qp(t)) is 0


class QTable(PrettyMixin):
    def __init__(self, tablename, engine, columns=None, dshape=None,
                 schema=None):
        self.tablename = tablename
        self.engine = engine
        self.dshape = dshape or discover(self)
        self.columns = columns or self.engine.eval('cols[%s]' %
                                                   self.tablename).tolist()
        self.schema = schema or self.dshape.measure

    def eval(self, expr, *args, **kwargs):
        return self.engine.eval('eval [%s]' % expr, *args, **kwargs)

    def _repr_pretty_(self, p, cycle):
        assert not cycle, 'cycles not allowed'
        name = type(self).__name__
        extra_indent = len(type(self).__name__)
        spaces = ' ' * extra_indent
        with p.group(len(name) + 1, '%s(' % name, ')'):
            p.text('tablename=%r' % self.tablename)
            p.text(',')
            p.breakable()
            s = str(self.dshape)
            s = s.replace('\n', '\n' + spaces)
            p.text('dshape="""%s"""' % s)

    @property
    def _qsymbol(self):
        return q.Symbol(self.tablename, is_partitioned=is_partitioned(self),
                        is_splayed=is_splayed(self))

    @property
    def iskeyed(self):
        sym = self._qsymbol
        return self.eval(q.and_(q.istable(sym), q.isdict(sym)))

    @property
    def keys(self):
        if self.iskeyed:
            expr = q.List('cols', q.List('key', self._qsymbol))
            return self.eval(expr).tolist()
        return []


@discover.register(QTable)
def discover_qtable(t):
    return tables(t.engine)[t.tablename].dshape


@discover.register(KQ)
def discover_kq(kq):
    return DataShape(Record([(k, v.dshape) for k, v in tables(kq).items()]))
