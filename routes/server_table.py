from flask import request, url_for
from sqlalchemy import String, cast, func, or_


def ist_date_filter_expr(created_at_col):
    """SQL expression matching what `ist()` displays for a naive-UTC
    `created_at` column (dd-mm-yyyy, IST = UTC+5:30) — for filtering/
    searching only, never for sorting (string-sorting dd-mm-yyyy text
    would not sort chronologically). SQLite-only (`datetime`/`strftime`),
    which is fine — this app is SQLite-only by design."""
    return func.strftime("%d-%m-%Y", func.datetime(created_at_col, "+5 hours", "+30 minutes"))


def date_filter_expr(date_col):
    """SQL expression matching how a plain business `date` column (already
    date-only, no timezone) is displayed (dd-mm-yyyy) — for filtering/
    searching a Purchase.date/Sale.date column, no IST offset needed since
    it isn't a UTC timestamp."""
    return func.strftime("%d-%m-%Y", date_col)


class ServerTable:
    """Search + per-column filter + sort + pagination pushed into the SQL
    query, for the tables whose row counts grow without bound (Sales,
    Purchases, Stock Ledger). Unlike the small master-data lists (Products,
    Customers, ...), which are handled client-side by data-table.js, those
    can't be loaded into the browser wholesale once they reach real volume
    — everything here happens as a real page load instead.

    `columns` maps a stable key -> (label, sort_expr, filter_expr).
    filter_expr may differ from sort_expr — e.g. Date sorts by the raw
    `created_at` (for correct chronological order) but filters/searches
    against a SQL-side IST-formatted string (since that's what `ist()`
    actually displays; substring-matching the raw UTC value would rarely
    match what the user typed). Pass None for either to disable that
    capability on the column; a 2-tuple (label, expr) is also accepted and
    uses the same expression for both.
    """

    def __init__(self, query, columns, search_keys=None, default_sort=None,
                 default_dir="desc", per_page=50, extra_args=None):
        self.columns = {
            key: (tup[0], tup[1], tup[2] if len(tup) > 2 else tup[1])
            for key, tup in columns.items()
        }
        self.extra_args = extra_args or {}
        args = request.args

        self.q = args.get("q", "").strip()
        if self.q:
            keys = search_keys if search_keys is not None else self.columns.keys()
            search_exprs = [self.columns[k][2] for k in keys if self.columns[k][2] is not None]
            if search_exprs:
                like = f"%{self.q}%"
                query = query.filter(or_(*[cast(e, String).ilike(like) for e in search_exprs]))

        self.filters = {}
        for key, (_label, _sort_expr, filter_expr) in self.columns.items():
            val = args.get(f"f_{key}", "").strip()
            self.filters[key] = val
            if val and filter_expr is not None:
                query = query.filter(cast(filter_expr, String).ilike(f"%{val}%"))

        self.sort = args.get("sort") or default_sort
        self.dir = args.get("dir") or default_dir
        sort_expr = self.columns.get(self.sort, (None, None, None))[1]
        if sort_expr is not None:
            query = query.order_by(sort_expr.desc() if self.dir == "desc" else sort_expr.asc())

        page = args.get("page", 1, type=int)
        self.pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        self.items = self.pagination.items

    @property
    def has_active_filters(self):
        return bool(self.q or any(self.filters.values()))

    def _base_args(self):
        out = dict(self.extra_args)
        if self.q:
            out["q"] = self.q
        for key, val in self.filters.items():
            if val:
                out[f"f_{key}"] = val
        return out

    def sort_url(self, key):
        args = self._base_args()
        args["sort"] = key
        args["dir"] = "desc" if (self.sort == key and self.dir == "asc") else "asc"
        return url_for(request.endpoint, **args)

    def sort_indicator(self, key):
        if self.sort != key:
            return "↕"
        return "▲" if self.dir == "asc" else "▼"

    def page_url(self, page_num):
        args = self._base_args()
        args["sort"] = self.sort
        args["dir"] = self.dir
        args["page"] = page_num
        return url_for(request.endpoint, **args)

    def clear_url(self):
        """Drops q/filters/sort but keeps extra_args (e.g. the Stock Ledger's
        date range) — "clear search/filters" without losing that context."""
        return url_for(request.endpoint, **self.extra_args)

    def filter_form_hidden(self):
        """(name, value) pairs the filter <form> re-emits as hidden inputs so
        submitting it preserves sort + any caller-supplied extra_args
        (e.g. the Stock Ledger's date range) instead of resetting them."""
        out = [("sort", self.sort), ("dir", self.dir)]
        out += list(self.extra_args.items())
        return out
