"""``cellview`` business package: lib / cell / view / category file management.

只调中层 execute_skill；SKILL 文本工具从 `pyapi.packages.basic` 复用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyapi.models import Middle
from pyapi.packages import basic


def _step(name: str, ok: bool, detail: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_timeout(timeout: Any) -> None:
    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
        raise ValueError("timeout must be a positive number or None")


@dataclass
class Result:
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    value: Any = None


@dataclass(frozen=True)
class LibListRequest:
    token: str
    timeout: int | None = None


@dataclass(frozen=True)
class LibGetRequest:
    token: str
    library: str
    timeout: int | None = None


@dataclass(frozen=True)
class LibCreateRequest:
    token: str
    library: str
    path: str
    technology_library: str | None = None
    timeout: int | None = None


@dataclass(frozen=True)
class LibCopyRequest:
    token: str
    library: str
    new_library: str
    new_path: str
    timeout: int | None = None


@dataclass(frozen=True)
class LibDeleteRequest:
    token: str
    library: str
    timeout: int | None = None


@dataclass(frozen=True)
class LibRenameRequest:
    token: str
    library: str
    new_name: str
    timeout: int | None = None


@dataclass(frozen=True)
class LibBindRequest:
    token: str
    library: str
    technology_library: str
    timeout: int | None = None


@dataclass(frozen=True)
class CellListRequest:
    token: str
    library: str
    category: str | None = None
    timeout: int | None = None


@dataclass(frozen=True)
class CellCopyRequest:
    token: str
    library: str
    cell: str
    new_library: str
    new_cell: str
    timeout: int | None = None


@dataclass(frozen=True)
class CellDeleteRequest:
    token: str
    library: str
    cell: str
    timeout: int | None = None


@dataclass(frozen=True)
class CellRenameRequest:
    token: str
    library: str
    cell: str
    new_name: str
    timeout: int | None = None


@dataclass(frozen=True)
class ViewListRequest:
    token: str
    library: str
    cell: str
    timeout: int | None = None


@dataclass(frozen=True)
class ViewCreateRequest:
    token: str
    library: str
    cell: str
    view: str
    view_type: str
    timeout: int | None = None


@dataclass(frozen=True)
class ViewCopyRequest:
    token: str
    library: str
    cell: str
    view: str
    new_library: str
    new_cell: str
    new_view: str
    timeout: int | None = None


@dataclass(frozen=True)
class ViewDeleteRequest:
    token: str
    library: str
    cell: str
    view: str
    timeout: int | None = None


@dataclass(frozen=True)
class ViewRenameRequest:
    token: str
    library: str
    cell: str
    view: str
    new_name: str
    timeout: int | None = None


@dataclass(frozen=True)
class CatListRequest:
    token: str
    library: str
    timeout: int | None = None


@dataclass(frozen=True)
class CatCreateRequest:
    token: str
    library: str
    category: str
    timeout: int | None = None


@dataclass(frozen=True)
class CatDeleteRequest:
    token: str
    library: str
    category: str
    timeout: int | None = None


@dataclass(frozen=True)
class CatRenameRequest:
    token: str
    library: str
    category: str
    new_name: str
    timeout: int | None = None


@dataclass(frozen=True)
class CatAddCellRequest:
    token: str
    library: str
    category: str
    cell: str
    timeout: int | None = None


@dataclass(frozen=True)
class CatRemoveCellRequest:
    token: str
    library: str
    category: str
    cell: str
    timeout: int | None = None


# ---- SKILL builders ----------------------------------------------------------

def _library_info_expr(var: str) -> str:
    return f'list("library" {var}~>name {var}~>readPath techGetTechLibName({var}))'


def _lib_list_skill() -> str:
    return 'list("ok" mapcar(lambda((vbLib) vbLib~>name) ddGetLibList()))'


def _lib_get_skill(name: str) -> str:
    return (f'let((vbLib) vbLib = ddGetObj({basic.q(name)}) '
            f'if(vbLib then list("ok" {_library_info_expr("vbLib")}) '
            'else list("error" "libraryNotFound")))')


def _lib_create_skill(name: str, path: str, tech: str | None) -> str:
    tech_expr = "nil" if tech is None else basic.q(tech)
    return f'''
let((vbLib vbTechName vbBound)
  vbTechName = {tech_expr}
  if(ddGetObj({basic.q(name)}) then list("error" "libraryExists")
  else if(vbTechName && !ddGetObj(vbTechName) then list("error" "technologyLibraryNotFound")
  else progn(
    vbLib = ddCreateLib({basic.q(name)} {basic.q(path)})
    if(!vbLib then list("error" "createFailed")
    else if(!vbTechName then list("ok" {_library_info_expr("vbLib")})
    else progn(
      vbBound = techBindTechFile(vbLib vbTechName)
      if(vbBound && techGetTechLibName(vbLib) == vbTechName
        then list("ok" {_library_info_expr("vbLib")})
        else list("partial" "technologyBindingFailed" {_library_info_expr("vbLib")}))))))))
)'''.strip()


def _lib_delete_skill(name: str) -> str:
    return (f'let((vbLib vbDeleted) vbLib = ddGetObj({basic.q(name)}) '
            'if(!vbLib then list("error" "libraryNotFound") else progn('
            'vbDeleted = ddDeleteObj(vbLib) '
            f'if(vbDeleted && !ddGetObj({basic.q(name)}) then list("ok") '
            'else list("error" "deleteFailed")))))')


def _lib_rename_skill(name: str, new_name: str) -> str:
    return f'''
let((vbSource vbDestination vbRenamed vbLib)
  if(!ddGetObj({basic.q(name)}) then list("error" "libraryNotFound")
  else if(ddGetObj({basic.q(new_name)}) then list("error" "destinationExists")
  else progn(
    vbSource = gdmCreateSpec({basic.q(name)} "" "" "" "CDBA")
    vbDestination = gdmCreateSpec({basic.q(new_name)} "" "" "" "CDBA")
    if(!vbSource || !vbDestination then list("error" "renameSpecFailed")
    else progn(
      vbRenamed = ccpRename(vbSource vbDestination nil)
      vbLib = ddGetObj({basic.q(new_name)})
      if(vbRenamed && vbLib && !ddGetObj({basic.q(name)})
        then list("ok" {_library_info_expr("vbLib")})
        else list("error" "renameFailed")))))))
)'''.strip()


def _lib_bind_skill(name: str, tech: str) -> str:
    return f'''
let((vbLib vbTechLib vbCurrent vbChanged)
  vbLib = ddGetObj({basic.q(name)})
  vbTechLib = ddGetObj({basic.q(tech)})
  if(!vbLib then list("error" "libraryNotFound")
  else if(!vbTechLib then list("error" "technologyLibraryNotFound")
  else progn(
    vbCurrent = techGetTechLibName(vbLib)
    vbChanged = if(vbCurrent then techSetTechLibName(vbLib {basic.q(tech)})
                  else techBindTechFile(vbLib {basic.q(tech)}))
    if(vbChanged && techGetTechLibName(vbLib) == {basic.q(tech)}
      then list("ok" {_library_info_expr("vbLib")})
      else list("error" "technologyBindingFailed"))))))
'''.strip()


def _cell_list_skill(library: str) -> str:
    return f'''
let((vbLib vbResult)
  vbLib = ddGetObj({basic.q(library)})
  if(!vbLib then list("error" "libraryNotFound")
  else progn(
    vbResult = nil
    foreach(vbCell vbLib~>cells vbResult = cons(vbCell~>name vbResult))
    list("ok" reverse(vbResult)))))
'''.strip()


def _cell_copy_skill(library: str, cell: str, new_library: str, new_cell: str) -> str:
    return f'''
let((vbLib vbNewLib vbCell vbAll vbSourceCv vbOk)
  vbLib = ddGetObj({basic.q(library)})
  vbNewLib = ddGetObj({basic.q(new_library)})
  vbCell = if(vbLib car(setof(vbC vbLib~>cells vbC~>name == {basic.q(cell)})) nil)
  if(!vbLib then list("error" "libraryNotFound")
  else if(!vbNewLib then list("error" "destinationLibraryNotFound")
  else if(!vbCell then list("error" "cellNotFound")
  else if(car(setof(vbC vbNewLib~>cells vbC~>name == {basic.q(new_cell)})) then list("error" "destinationExists")
  else progn(
    vbAll = t
    foreach(vbView vbCell~>views
      unless(progn(
        vbSourceCv = dbOpenCellViewByType({basic.q(library)} {basic.q(cell)}
                                         vbView~>name vbView~>viewType "r")
        if(vbSourceCv then
          unwindProtect(
            progn(
              vbOk = dbCopyCellView(vbSourceCv {basic.q(new_library)}
                                    {basic.q(new_cell)} vbView~>name)
              when(vbOk dbClose(vbOk))
              vbOk)
            progn(when(vbSourceCv dbClose(vbSourceCv))))
        else nil))
        vbAll = nil))
    if(vbAll then list("ok") else list("error" "copyFailed")))))))
)'''.strip()


def _cell_delete_skill(library: str, cell: str) -> str:
    return f'''
let((vbLib vbCell vbDeleted)
  vbLib = ddGetObj({basic.q(library)})
  vbCell = if(vbLib car(setof(vbC vbLib~>cells vbC~>name == {basic.q(cell)})) nil)
  if(!vbLib then list("error" "libraryNotFound")
  else if(!vbCell then list("error" "cellNotFound")
  else progn(
    vbDeleted = ddDeleteObj(vbCell)
    if(vbDeleted && !member({basic.q(cell)} vbLib~>cells~>name)
      then list("ok") else list("error" "deleteFailed")))))
)'''.strip()


def _cell_rename_skill(library: str, cell: str, new_name: str) -> str:
    return f'''
let((vbLib vbCell vbSource vbDestination vbRenamed)
  vbLib = ddGetObj({basic.q(library)})
  vbCell = if(vbLib car(setof(vbC vbLib~>cells vbC~>name == {basic.q(cell)})) nil)
  if(!vbLib then list("error" "libraryNotFound")
  else if(!vbCell then list("error" "cellNotFound")
  else if(car(setof(vbC vbLib~>cells vbC~>name == {basic.q(new_name)})) then list("error" "destinationExists")
  else progn(
    vbSource = gdmCreateSpec({basic.q(library)} {basic.q(cell)} "" "" "CDBA")
    vbDestination = gdmCreateSpec({basic.q(library)} {basic.q(new_name)} "" "" "CDBA")
    vbRenamed = ccpRename(vbSource vbDestination nil)
    if(vbRenamed && !member({basic.q(cell)} vbLib~>cells~>name)
      then list("ok") else list("error" "renameFailed")))))))
'''.strip()


def _view_list_skill(library: str, cell: str) -> str:
    return f'''
let((vbLib vbCell vbResult)
  vbLib = ddGetObj({basic.q(library)})
  vbCell = if(vbLib car(setof(vbC vbLib~>cells vbC~>name == {basic.q(cell)})) nil)
  if(!vbLib then list("error" "libraryNotFound")
  else if(!vbCell then list("error" "cellNotFound")
  else progn(
    vbResult = nil
    foreach(vbView vbCell~>views
      vbResult = cons(list(vbView~>name vbView~>viewType) vbResult))
    list("ok" reverse(vbResult)))))
)'''.strip()


def _view_create_skill(library: str, cell: str, view: str, view_type: str) -> str:
    return f'''
let((vbCv vbSaved)
  vbCv = dbOpenCellViewByType({basic.q(library)} {basic.q(cell)} {basic.q(view)}
                              {basic.q(view_type)} "w")
  if(!vbCv then list("error" "createFailed")
  else progn(
    vbSaved = dbSave(vbCv)
    dbClose(vbCv)
    if(vbSaved then list("ok") else list("error" "saveFailed")))))
'''.strip()


def _view_copy_skill(library: str, cell: str, view: str,
                     new_library: str, new_cell: str, new_view: str) -> str:
    return f'''
let((vbLib vbNewLib vbCell vbView vbSourceCv vbCopied)
  vbLib = ddGetObj({basic.q(library)})
  vbNewLib = ddGetObj({basic.q(new_library)})
  vbCell = if(vbLib car(setof(vbC vbLib~>cells vbC~>name == {basic.q(cell)})) nil)
  vbView = if(vbCell car(setof(vbV vbCell~>views vbV~>name == {basic.q(view)})) nil)
  if(!vbLib then list("error" "libraryNotFound")
  else if(!vbNewLib then list("error" "destinationLibraryNotFound")
  else if(!vbView then list("error" "viewNotFound")
  else progn(
    vbSourceCv = dbOpenCellViewByType({basic.q(library)} {basic.q(cell)}
                                      {basic.q(view)} vbView~>viewType "r")
    if(!vbSourceCv then list("error" "viewOpenFailed")
    else progn(
      vbCopied = unwindProtect(
        progn(
          vbCopied = dbCopyCellView(vbSourceCv {basic.q(new_library)}
                                    {basic.q(new_cell)} {basic.q(new_view)})
          when(vbCopied dbClose(vbCopied))
          vbCopied)
        progn(when(vbSourceCv dbClose(vbSourceCv))))
      if(vbCopied then list("ok") else list("error" "copyFailed")))))))))
'''.strip()


def _view_delete_skill(library: str, cell: str, view: str) -> str:
    return f'''
let((vbLib vbCell vbView vbDeleted)
  vbLib = ddGetObj({basic.q(library)})
  vbCell = if(vbLib car(setof(vbC vbLib~>cells vbC~>name == {basic.q(cell)})) nil)
  vbView = if(vbCell car(setof(vbV vbCell~>views vbV~>name == {basic.q(view)})) nil)
  if(!vbLib then list("error" "libraryNotFound")
  else if(!vbCell then list("error" "cellNotFound")
  else if(!vbView then list("error" "viewNotFound")
  else progn(
    vbDeleted = ddDeleteObj(vbView)
    if(vbDeleted && !member({basic.q(view)} vbCell~>views~>name)
      then list("ok") else list("error" "deleteFailed")))))))
'''.strip()


def _view_rename_skill(library: str, cell: str, view: str, new_name: str) -> str:
    return f'''
let((vbLib vbCell vbSource vbDestination vbRenamed)
  vbLib = ddGetObj({basic.q(library)})
  vbCell = if(vbLib car(setof(vbC vbLib~>cells vbC~>name == {basic.q(cell)})) nil)
  if(!vbLib then list("error" "libraryNotFound")
  else if(!vbCell then list("error" "cellNotFound")
  else if(car(setof(vbV vbCell~>views vbV~>name == {basic.q(new_name)})) then list("error" "destinationExists")
  else progn(
    vbSource = gdmCreateSpec({basic.q(library)} {basic.q(cell)} {basic.q(view)} "" "CDBA")
    vbDestination = gdmCreateSpec({basic.q(library)} {basic.q(cell)} {basic.q(new_name)} "" "CDBA")
    vbRenamed = ccpRename(vbSource vbDestination nil)
    if(vbRenamed && !member({basic.q(view)} vbCell~>views~>name)
      then list("ok") else list("error" "renameFailed")))))))
'''.strip()


def _cat_list_skill(library: str) -> str:
    return f'''
let((vbLib vbName vbCat vbClosed vbResult)
  vbLib = ddGetObj({basic.q(library)})
  if(!vbLib then list("error" "libraryNotFound")
  else progn(
    vbResult = nil
    foreach(vbName ddCatGetLibCats(vbLib)
      vbCat = ddCatOpen(vbLib vbName "r")
      when(vbCat
        vbResult = cons(vbName vbResult)
        vbClosed = ddCatClose(vbCat)
        unless(vbClosed error("category close failed"))))
    list("ok" reverse(vbResult)))))
'''.strip()


def _cat_list_cells_skill(library: str, category: str) -> str:
    return f'''
let((vbLib vbCat vbMember vbCells vbClosed)
  vbLib = ddGetObj({basic.q(library)})
  if(!vbLib then list("error" "libraryNotFound")
  else progn(
    vbCat = ddCatOpen(vbLib {basic.q(category)} "r")
    if(!vbCat then list("error" "categoryNotFound")
    else progn(
      vbCells = nil
      foreach(vbMember ddCatGetCatMembers(vbCat)
        when(cadr(vbMember) == "cell" vbCells = cons(car(vbMember) vbCells)))
      vbClosed = ddCatClose(vbCat)
      if(vbClosed then list("ok" reverse(vbCells))
      else list("error" "categoryCloseFailed"))))))
)'''.strip()


def _cat_create_skill(library: str, category: str) -> str:
    return f'''
let((vbLib vbExisting vbCat vbSaved vbClosed vbVerify)
  vbLib = ddGetObj({basic.q(library)})
  if(!vbLib then list("error" "libraryNotFound")
  else progn(
    vbExisting = ddCatOpen(vbLib {basic.q(category)} "r")
    if(vbExisting then progn(
      vbClosed = ddCatClose(vbExisting)
      if(vbClosed then list("error" "categoryExists")
      else list("error" "categoryCloseFailed")))
    else progn(
      vbCat = ddCatOpenEx(vbLib {basic.q(category)} "w" 1)
      if(!vbCat then list("error" "categoryCreateFailed")
      else progn(
        vbSaved = ddCatSave(vbCat)
        vbClosed = ddCatClose(vbCat)
        if(!vbSaved || !vbClosed then list("partial" "categoryCreateFailed")
        else progn(
          vbVerify = ddCatOpen(vbLib {basic.q(category)} "r")
          if(!vbVerify then list("partial" "categoryCreateVerificationFailed")
          else progn(
            vbClosed = ddCatClose(vbVerify)
            if(vbClosed then list("ok" {basic.q(category)})
            else list("partial" "categoryCloseFailed")))))))))))
))'''.strip()


def _cat_delete_skill(library: str, category: str) -> str:
    return f'''
let((vbLib vbExisting vbCat vbRemoved vbClosed vbVerify)
  vbLib = ddGetObj({basic.q(library)})
  if(!vbLib then list("error" "libraryNotFound")
  else progn(
    vbExisting = ddCatOpen(vbLib {basic.q(category)} "r")
    if(!vbExisting then list("error" "categoryNotFound")
    else progn(
      vbClosed = ddCatClose(vbExisting)
      if(!vbClosed then list("error" "categoryCloseFailed")
      else progn(
        vbCat = ddCatOpen(vbLib {basic.q(category)} "a")
        if(!vbCat then list("error" "categoryReopenFailed")
        else progn(
          vbRemoved = ddCatRemove(vbCat)
          if(!vbRemoved then progn(ddCatClose(vbCat)
            list("error" "categoryDeleteFailed"))
          else progn(
            vbVerify = ddCatOpen(vbLib {basic.q(category)} "r")
            if(vbVerify then progn(ddCatClose(vbVerify)
              list("partial" "categoryDeleteVerificationFailed"))
            else list("ok")))))))))))
))'''.strip()


def _cat_rename_skill(library: str, category: str, new_name: str) -> str:
    return f'''
let((vbLib vbSource vbDestination vbExisting vbMember vbMembers vbDestinationMembers
     vbUnsupported vbAdded vbSaved vbClosed vbMatch vbRemoved vbVerify)
  vbLib = ddGetObj({basic.q(library)})
  if(!vbLib then list("error" "libraryNotFound")
  else progn(
    vbSource = ddCatOpen(vbLib {basic.q(category)} "r")
    if(!vbSource then list("error" "categoryNotFound")
    else progn(
      vbMembers = ddCatGetCatMembers(vbSource)
      vbUnsupported = nil
      foreach(vbMember vbMembers unless(cadr(vbMember) == "cell" vbUnsupported = t))
      vbClosed = ddCatClose(vbSource)
      if(!vbClosed then list("error" "categoryCloseFailed")
      else if(vbUnsupported then list("error" "categoryContainsSubcategories")
      else progn(
        vbExisting = ddCatOpen(vbLib {basic.q(new_name)} "r")
        if(vbExisting then progn(ddCatClose(vbExisting)
          list("error" "destinationCategoryExists"))
        else progn(
          vbDestination = ddCatOpenEx(vbLib {basic.q(new_name)} "w" 1)
          if(!vbDestination then list("error" "categoryRenameCreateFailed")
          else progn(
            vbAdded = t
            foreach(vbMember vbMembers
              unless(ddCatAddItem(vbDestination car(vbMember) cadr(vbMember)) vbAdded = nil))
            vbSaved = if(vbAdded then ddCatSave(vbDestination) else nil)
            vbClosed = ddCatClose(vbDestination)
            if(!vbAdded || !vbSaved || !vbClosed then list("partial" "categoryRenameDestinationFailed")
            else progn(
              vbVerify = ddCatOpen(vbLib {basic.q(new_name)} "r")
              if(!vbVerify then list("partial" "categoryRenameVerificationFailed")
              else progn(
                vbDestinationMembers = ddCatGetCatMembers(vbVerify)
                vbMatch = length(vbMembers) == length(vbDestinationMembers)
                foreach(vbMember vbMembers unless(member(vbMember vbDestinationMembers) vbMatch = nil))
                vbClosed = ddCatClose(vbVerify)
                if(!vbMatch || !vbClosed then list("partial" "categoryRenameVerificationFailed")
                else progn(
                  vbSource = ddCatOpen(vbLib {basic.q(category)} "a")
                  if(!vbSource then list("partial" "categoryRenameSourceReopenFailed")
                  else progn(
                    vbRemoved = ddCatRemove(vbSource)
                    if(!vbRemoved then progn(ddCatClose(vbSource)
                      list("partial" "categoryRenameSourceRemovalFailed"))
                    else progn(
                      vbVerify = ddCatOpen(vbLib {basic.q(category)} "r")
                      if(vbVerify then progn(ddCatClose(vbVerify)
                        list("partial" "categoryRenameSourceVerificationFailed"))
                      else list("ok" {basic.q(new_name)})))))))))))))))))
)))))))'''.strip()


def _cat_change_cell_skill(library: str, category: str, cell: str, *, add: bool) -> str:
    present_error = "cellAlreadyInCategory" if add else "cellNotInCategory"
    change = (f'ddCatAddItem(vbCat {basic.q(cell)} "cell")' if add
              else f"ddCatSubItem(vbCat {basic.q(cell)})")
    expected = "t" if add else "nil"
    return f'''
let((vbLib vbCell vbCat vbMembers vbPresent vbChanged vbSaved vbClosed vbVerify)
  vbLib = ddGetObj({basic.q(library)})
  if(!vbLib then list("error" "libraryNotFound")
  else progn(
    vbCell = member({basic.q(cell)} vbLib~>cells~>name)
    if(!vbCell then list("error" "cellNotFound")
    else progn(
      vbCat = ddCatOpen(vbLib {basic.q(category)} "r")
      if(!vbCat then list("error" "categoryNotFound")
      else progn(
        vbMembers = ddCatGetCatMembers(vbCat)
        vbPresent = if(member(list({basic.q(cell)} "cell") vbMembers) t nil)
        vbClosed = ddCatClose(vbCat)
        if(!vbClosed then list("error" "categoryCloseFailed")
        else if(vbPresent == {expected} then list("error" "{present_error}")
        else progn(
          vbCat = ddCatOpen(vbLib {basic.q(category)} "a")
          if(!vbCat then list("error" "categoryReopenFailed")
          else progn(
            vbChanged = {change}
            vbSaved = if(vbChanged then ddCatSave(vbCat) else nil)
            vbClosed = ddCatClose(vbCat)
            if(!vbChanged || !vbSaved || !vbClosed then list("partial" "categoryMembershipChangeFailed")
            else progn(
              vbVerify = ddCatOpen(vbLib {basic.q(category)} "r")
              if(!vbVerify then list("partial" "categoryMembershipVerificationFailed")
              else progn(
                vbMembers = ddCatGetCatMembers(vbVerify)
                vbPresent = if(member(list({basic.q(cell)} "cell") vbMembers) t nil)
                vbClosed = ddCatClose(vbVerify)
                if(vbClosed && vbPresent == {expected} then list("ok")
                else list("partial" "categoryMembershipVerificationFailed"))))))))))))))
))))'''.strip()
# ---- package ------------------------------------------------------------------

class Package:
    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    def _run_skill(self, token: str, timeout: int | None, skill: str,
                   step_name: str) -> Result:
        res = self.middle.execute_skill(skill, timeout=timeout, token=token)
        steps = [_step(step_name, res.ok, res)]
        if not res.ok:
            return Result(False, steps, "; ".join(res.errors) or "skill failed")
        text = (res.output or "").strip()
        if not basic.is_single_complete_skill_list(text):
            return Result(False, steps, "malformed skill result")
        record = basic.parse_sexpr(text)
        if not isinstance(record, list) or not record or not isinstance(record[0], str):
            return Result(False, steps, "malformed skill result")
        if record[0] == "ok":
            value = record[1] if len(record) > 1 else None
            return Result(True, steps, None, value)
        code = record[1] if len(record) > 1 else "skillFailed"
        return Result(False, steps, str(code))

    # lib ----------------------------------------------------------------------
    def lib_list(self, request: LibListRequest) -> Result:
        _require_text(request.token, "token")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout, _lib_list_skill(), "list")

    def lib_get(self, request: LibGetRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        _require_timeout(request.timeout)
        result = self._run_skill(request.token, request.timeout,
                                 _lib_get_skill(library), "get")
        if result.ok and isinstance(result.value, list) and len(result.value) == 4:
            result.value = {"name": result.value[1], "path": result.value[2],
                            "technology_library": result.value[3]}
        return result

    def lib_create(self, request: LibCreateRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        path = _require_text(request.path, "path")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _lib_create_skill(library, path, request.technology_library), "create")

    def lib_copy(self, request: LibCopyRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        new_library = _require_text(request.new_library, "new_library")
        new_path = _require_text(request.new_path, "new_path")
        _require_timeout(request.timeout)
        created = self._run_skill(request.token, request.timeout,
                                  _lib_create_skill(new_library, new_path, None), "create")
        if not created.ok:
            return created
        steps = list(created.steps)
        cells = self._run_skill(request.token, request.timeout,
                                _cell_list_skill(library), "list_cells")
        steps.extend(cells.steps)
        if not cells.ok:
            return Result(False, steps, cells.error)
        for cell in cells.value or []:
            copied = self._run_skill(request.token, request.timeout,
                                     _cell_copy_skill(library, str(cell),
                                                      new_library, str(cell)), f"copy_cell:{cell}")
            steps.extend(copied.steps)
            if not copied.ok:
                return Result(False, steps, copied.error)
        return Result(True, steps)

    def lib_delete(self, request: LibDeleteRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _lib_delete_skill(library), "delete")

    def lib_rename(self, request: LibRenameRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        new_name = _require_text(request.new_name, "new_name")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _lib_rename_skill(library, new_name), "rename")

    def lib_bind(self, request: LibBindRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        tech = _require_text(request.technology_library, "technology_library")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _lib_bind_skill(library, tech), "bind")

    # cell ---------------------------------------------------------------------
    def cell_list(self, request: CellListRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        _require_timeout(request.timeout)
        if request.category is not None:
            category = _require_text(request.category, "category")
            return self._run_skill(request.token, request.timeout,
                                   _cat_list_cells_skill(library, category), "list")
        return self._run_skill(request.token, request.timeout,
                               _cell_list_skill(library), "list")

    def cell_copy(self, request: CellCopyRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        cell = _require_text(request.cell, "cell")
        new_library = _require_text(request.new_library, "new_library")
        new_cell = _require_text(request.new_cell, "new_cell")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _cell_copy_skill(library, cell, new_library, new_cell), "copy")

    def cell_delete(self, request: CellDeleteRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        cell = _require_text(request.cell, "cell")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _cell_delete_skill(library, cell), "delete")

    def cell_rename(self, request: CellRenameRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        cell = _require_text(request.cell, "cell")
        new_name = _require_text(request.new_name, "new_name")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _cell_rename_skill(library, cell, new_name), "rename")

    # view ---------------------------------------------------------------------
    def view_list(self, request: ViewListRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        cell = _require_text(request.cell, "cell")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _view_list_skill(library, cell), "list")

    def view_create(self, request: ViewCreateRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        cell = _require_text(request.cell, "cell")
        view = _require_text(request.view, "view")
        view_type = _require_text(request.view_type, "view_type")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _view_create_skill(library, cell, view, view_type), "create")

    def view_copy(self, request: ViewCopyRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        cell = _require_text(request.cell, "cell")
        view = _require_text(request.view, "view")
        new_library = _require_text(request.new_library, "new_library")
        new_cell = _require_text(request.new_cell, "new_cell")
        new_view = _require_text(request.new_view, "new_view")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _view_copy_skill(library, cell, view, new_library, new_cell, new_view), "copy")

    def view_delete(self, request: ViewDeleteRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        cell = _require_text(request.cell, "cell")
        view = _require_text(request.view, "view")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _view_delete_skill(library, cell, view), "delete")

    def view_rename(self, request: ViewRenameRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        cell = _require_text(request.cell, "cell")
        view = _require_text(request.view, "view")
        new_name = _require_text(request.new_name, "new_name")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _view_rename_skill(library, cell, view, new_name), "rename")

    # category -----------------------------------------------------------------
    def cat_list(self, request: CatListRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _cat_list_skill(library), "list")

    def cat_create(self, request: CatCreateRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        category = _require_text(request.category, "category")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _cat_create_skill(library, category), "create")

    def cat_delete(self, request: CatDeleteRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        category = _require_text(request.category, "category")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _cat_delete_skill(library, category), "delete")

    def cat_rename(self, request: CatRenameRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        category = _require_text(request.category, "category")
        new_name = _require_text(request.new_name, "new_name")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _cat_rename_skill(library, category, new_name), "rename")

    def cat_add_cell(self, request: CatAddCellRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        category = _require_text(request.category, "category")
        cell = _require_text(request.cell, "cell")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _cat_change_cell_skill(library, category, cell, add=True), "add_cell")

    def cat_remove_cell(self, request: CatRemoveCellRequest) -> Result:
        _require_text(request.token, "token")
        library = _require_text(request.library, "library")
        category = _require_text(request.category, "category")
        cell = _require_text(request.cell, "cell")
        _require_timeout(request.timeout)
        return self._run_skill(request.token, request.timeout,
                               _cat_change_cell_skill(library, category, cell, add=False), "remove_cell")


OPERATIONS = (
    ("virtuoso.cellview.lib.list", "lib_list", LibListRequest, Result),
    ("virtuoso.cellview.lib.get", "lib_get", LibGetRequest, Result),
    ("virtuoso.cellview.lib.create", "lib_create", LibCreateRequest, Result),
    ("virtuoso.cellview.lib.copy", "lib_copy", LibCopyRequest, Result),
    ("virtuoso.cellview.lib.delete", "lib_delete", LibDeleteRequest, Result),
    ("virtuoso.cellview.lib.rename", "lib_rename", LibRenameRequest, Result),
    ("virtuoso.cellview.lib.bind", "lib_bind", LibBindRequest, Result),
    ("virtuoso.cellview.cell.list", "cell_list", CellListRequest, Result),
    ("virtuoso.cellview.cell.copy", "cell_copy", CellCopyRequest, Result),
    ("virtuoso.cellview.cell.delete", "cell_delete", CellDeleteRequest, Result),
    ("virtuoso.cellview.cell.rename", "cell_rename", CellRenameRequest, Result),
    ("virtuoso.cellview.view.list", "view_list", ViewListRequest, Result),
    ("virtuoso.cellview.view.create", "view_create", ViewCreateRequest, Result),
    ("virtuoso.cellview.view.copy", "view_copy", ViewCopyRequest, Result),
    ("virtuoso.cellview.view.delete", "view_delete", ViewDeleteRequest, Result),
    ("virtuoso.cellview.view.rename", "view_rename", ViewRenameRequest, Result),
    ("virtuoso.cellview.cat.list", "cat_list", CatListRequest, Result),
    ("virtuoso.cellview.cat.create", "cat_create", CatCreateRequest, Result),
    ("virtuoso.cellview.cat.delete", "cat_delete", CatDeleteRequest, Result),
    ("virtuoso.cellview.cat.rename", "cat_rename", CatRenameRequest, Result),
    ("virtuoso.cellview.cat.add_cell", "cat_add_cell", CatAddCellRequest, Result),
    ("virtuoso.cellview.cat.remove_cell", "cat_remove_cell", CatRemoveCellRequest, Result),
)

__all__ = ["OPERATIONS", "Package", "Result"]
