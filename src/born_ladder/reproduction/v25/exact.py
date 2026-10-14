"""Rational enclosures and nearest-even rounding cells; no floating solver."""
from fractions import Fraction as Q
from math import isqrt, isfinite, nextafter, inf
import struct


class Unresolved(ValueError):
    """Finite registered refinement exhausted; never an arbitrary substitute."""


def rational(value):
    if isinstance(value, Q): return value
    if type(value) is float:
        if not isfinite(value): raise ValueError('non-finite input')
        return Q.from_float(value)
    if type(value) is int: return Q(value)
    if isinstance(value, str): return Q(value)
    raise ValueError('exact input requires binary64, integer or rational string')


def square_root(q, bits):
    q = rational(q)
    if q < 0: raise ValueError('negative root')
    numerator, denominator = isqrt(q.numerator), isqrt(q.denominator)
    if numerator*numerator == q.numerator and denominator*denominator == q.denominator:
        return Interval(Q(numerator,denominator))
    scale = 1 << bits
    lower = isqrt((q.numerator << (2*bits)) // q.denominator)
    return Interval(Q(lower,scale),Q(lower+1,scale))


class Interval:
    def __init__(self, lo, hi=None):
        self.lo=rational(lo); self.hi=self.lo if hi is None else rational(hi)
        if self.lo > self.hi: raise ValueError('reversed interval')
    def __add__(self, other):
        other=as_interval(other); return Interval(self.lo+other.lo,self.hi+other.hi)
    __radd__=__add__
    def __neg__(self): return Interval(-self.hi,-self.lo)
    def __sub__(self, other): return self+-as_interval(other)
    def __mul__(self, other):
        other=as_interval(other)
        values=[a*b for a in (self.lo,self.hi) for b in (other.lo,other.hi)]
        return Interval(min(values),max(values))
    __rmul__=__mul__
    def __truediv__(self, other):
        other=as_interval(other)
        if other.lo<=0<=other.hi: raise Unresolved('division enclosure contains zero')
        return self*Interval(1/other.hi,1/other.lo)
    def square(self):
        return Interval(0 if self.lo<=0<=self.hi else min(self.lo**2,self.hi**2),
                        max(self.lo**2,self.hi**2))
    def absolute(self):
        return Interval(0 if self.lo<=0<=self.hi else min(abs(self.lo),abs(self.hi)),
                        max(abs(self.lo),abs(self.hi)))
    def data(self): return [str(self.lo),str(self.hi)]


def as_interval(value): return value if isinstance(value,Interval) else Interval(value)


def round_cell(interval, exact_equal=None):
    """Python rational-to-float is correctly rounded; prove a unique cell.

    When the enclosure straddles a binary64 midpoint, equality must be proved
    by the caller's exact algebraic expression before ties-to-even is used.
    """
    lo,hi=float(interval.lo),float(interval.hi)
    if not isfinite(lo) or not isfinite(hi): raise Unresolved('non-finite rounding cell')
    if struct.pack('>d',lo)==struct.pack('>d',hi):
        return (0.0 if interval.lo==interval.hi==0 else lo), {'interval':interval.data(),'midpoint_equality':False}
    if nextafter(lo,inf)==hi:
        midpoint=(Q.from_float(lo)+Q.from_float(hi))/2
        if exact_equal is not None and exact_equal(midpoint):
            return float(midpoint), {'interval':interval.data(),'midpoint_equality':str(midpoint)}
    raise Unresolved('enclosure crosses rounding cells')
