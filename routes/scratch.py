from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

from extensions import db
from excel_sync import sync_to_excel
from models import ScratchSheet
from routes.reports import _safe_filename, _send_excel

scratch_bp = Blueprint("scratch", __name__, url_prefix="/scratch")

DEFAULT_COLUMNS = ["Column 1", "Column 2", "Column 3"]
DEFAULT_ROWS = 8


def _limits():
    """The caps the editor prints and its JS guards on — kept on the model so
    the server and the page can't disagree about them."""
    return {"max_columns": ScratchSheet.MAX_COLUMNS, "max_rows": ScratchSheet.MAX_ROWS}


def _read_grid_from_form():
    """Reads the grid out of the parallel column[]/cell[] arrays the editor
    posts. cell[] is one flat list for the whole grid, reshaped using the
    column count — which is only valid because every row always submits
    exactly len(columns) inputs. A leftover remainder means the DOM and the
    posted data disagree, so bail loudly instead of saving a shifted grid.

    Returns (columns, rows, error)."""
    columns = [c.strip() for c in request.form.getlist("column[]")]
    cells = request.form.getlist("cell[]")

    if not columns:
        return None, None, "A sheet needs at least one column."
    if len(columns) > ScratchSheet.MAX_COLUMNS:
        return None, None, f"A sheet can have at most {ScratchSheet.MAX_COLUMNS} columns."
    if len(cells) % len(columns) != 0:
        return None, None, "The sheet couldn't be read back correctly — reload the page and try again."

    rows = [cells[i:i + len(columns)] for i in range(0, len(cells), len(columns))]
    if len(rows) > ScratchSheet.MAX_ROWS:
        return None, None, f"A sheet can have at most {ScratchSheet.MAX_ROWS} rows."
    return columns, rows, None


@scratch_bp.route("/")
@login_required
def list_sheets():
    sheets = ScratchSheet.query.order_by(ScratchSheet.updated_at.desc()).all()
    return render_template("scratch/list.html", sheets=sheets)


@scratch_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_sheet():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        columns, rows, error = _read_grid_from_form()
        if not name:
            error = "Give the sheet a name."
        if error:
            flash(error, "danger")
            return render_template(
                "scratch/form.html", sheet=None, **_limits(),
                columns=columns or DEFAULT_COLUMNS,
                rows=rows or [["" for _ in DEFAULT_COLUMNS] for _ in range(DEFAULT_ROWS)],
            )

        sheet = ScratchSheet(name=name, note=request.form.get("note", "").strip())
        sheet.set_grid(columns, rows)
        db.session.add(sheet)
        db.session.commit()
        sync_to_excel()
        flash("Sheet saved.", "success")
        return redirect(url_for("scratch.edit_sheet", sheet_id=sheet.id))

    return render_template(
        "scratch/form.html", sheet=None, columns=DEFAULT_COLUMNS, **_limits(),
        rows=[["" for _ in DEFAULT_COLUMNS] for _ in range(DEFAULT_ROWS)],
    )


@scratch_bp.route("/<int:sheet_id>", methods=["GET", "POST"])
@login_required
def edit_sheet(sheet_id):
    sheet = ScratchSheet.query.get_or_404(sheet_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        columns, rows, error = _read_grid_from_form()
        if not name:
            error = "Give the sheet a name."
        if error:
            flash(error, "danger")
            return render_template(
                "scratch/form.html", sheet=sheet, **_limits(),
                columns=columns or sheet.column_list, rows=rows or sheet.row_list,
            )

        sheet.name = name
        sheet.note = request.form.get("note", "").strip()
        sheet.set_grid(columns, rows)
        db.session.commit()
        sync_to_excel()
        flash("Sheet saved.", "success")
        return redirect(url_for("scratch.edit_sheet", sheet_id=sheet.id))

    # A spare blank row so there's always somewhere to start typing.
    rows = sheet.row_list
    rows.append(["" for _ in sheet.column_list])
    return render_template("scratch/form.html", sheet=sheet, columns=sheet.column_list, rows=rows, **_limits())


@scratch_bp.route("/<int:sheet_id>/delete", methods=["POST"])
@login_required
def delete_sheet(sheet_id):
    sheet = ScratchSheet.query.get_or_404(sheet_id)
    db.session.delete(sheet)
    db.session.commit()
    sync_to_excel()
    flash("Sheet deleted.", "success")
    return redirect(url_for("scratch.list_sheets"))


@scratch_bp.route("/<int:sheet_id>/export")
@login_required
def export_sheet(sheet_id):
    sheet = ScratchSheet.query.get_or_404(sheet_id)
    return _send_excel(
        [(sheet.name[:31] or "Sheet", sheet.column_list, sheet.row_list)],
        f"{_safe_filename(sheet.name)}.xlsx",
    )
