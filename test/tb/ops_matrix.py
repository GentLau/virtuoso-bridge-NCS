"""List all upper-layer operations (from package source) for the coverage matrix."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def operation_names(package_file: Path) -> list[str]:
    tree = ast.parse(package_file.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "OPERATIONS":
                    if isinstance(node.value, (ast.Tuple, ast.List)):
                        for element in node.value.elts:
                            if isinstance(element, ast.Tuple) and element.elts:
                                first = element.elts[0]
                                if isinstance(first, ast.Constant):
                                    names.append(first.value)
    return names


def main() -> None:
    packages = sorted((ROOT / "src" / "pyapi" / "packages").glob("*.py"))
    total = 0
    for package in packages:
        if package.name.startswith("_"):
            continue
        names = operation_names(package)
        if names:
            total += len(names)
            print(f"{package.name:22} {len(names):2}  {', '.join(names)}")
    print(f"TOTAL {total}")


if __name__ == "__main__":
    main()
