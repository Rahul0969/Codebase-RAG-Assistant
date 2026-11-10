"""Tests for C12 static code change impact analysis."""
import tempfile
import unittest
from pathlib import Path

from backend.app.impact_service import analyze_change_impact


class ImpactServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "src" / "services").mkdir(parents=True)
        (self.root / "tests").mkdir()
        (self.root / "src" / "services" / "helper.py").write_text("def calculate():\n    return 42\n", encoding="utf-8")
        (self.root / "src" / "main.py").write_text("from src.services import helper\n\ndef run():\n    return helper.calculate()\n", encoding="utf-8")
        (self.root / "src" / "consumer.py").write_text("from src import main\n\ndef start():\n    return main.run()\n", encoding="utf-8")
        (self.root / "tests" / "test_helper.py").write_text("from src.services import helper\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_finds_direct_and_transitive_dependents_and_tests(self):
        result = analyze_change_impact(str(self.root), ["src/services/helper.py"])
        self.assertIn("src/main.py", result["direct_dependents"])
        self.assertIn("src/consumer.py", result["transitive_dependents"])
        self.assertIn("tests/test_helper.py", result["related_tests"])
        self.assertGreaterEqual(len(result["dependency_edges"]), 2)

    def test_rejects_traversal_and_unknown_paths(self):
        with self.assertRaises(ValueError):
            analyze_change_impact(str(self.root), ["../outside.py"])
        with self.assertRaises(ValueError):
            analyze_change_impact(str(self.root), ["missing.py"])

    def test_rejects_empty_and_too_many_changed_files(self):
        with self.assertRaises(ValueError):
            analyze_change_impact(str(self.root), [])
        with self.assertRaises(ValueError):
            analyze_change_impact(str(self.root), ["src/services/helper.py"] * 21)

    def test_detects_javascript_relative_imports(self):
        (self.root / "src" / "ui").mkdir()
        (self.root / "src" / "services" / "helper.js").write_text("export function helper() {}\n", encoding="utf-8")
        (self.root / "src" / "ui" / "panel.jsx").write_text(
            "import { helper } from '../services/helper';\nexport default helper;\n", encoding="utf-8")
        result = analyze_change_impact(str(self.root), ["src/services/helper.js"])
        self.assertIn("src/ui/panel.jsx", result["direct_dependents"])

    def test_detects_cycle_involving_changed_file(self):
        (self.root / "src" / "services" / "helper.py").write_text(
            "from src import main\ndef calculate(): return 42\n", encoding="utf-8")
        result = analyze_change_impact(str(self.root), ["src/services/helper.py"])
        self.assertTrue(result["possible_dependency_cycle"])
        self.assertIn("src/services/helper.py", result["cycle_involving_changed_files"])

    def test_no_false_positive_cycle_when_graph_is_acyclic(self):
        result = analyze_change_impact(str(self.root), ["src/services/helper.py"])
        self.assertFalse(result["possible_dependency_cycle"])


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Refined C12 edge-case tests
# ---------------------------------------------------------------------------
import os
from unittest.mock import patch


def _write(root, relative, text=""):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ImpactEdgeCaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def run_impact(self, files):
        return analyze_change_impact(str(self.root), files)

    # --- Python ---------------------------------------------------------
    def test_python_relative_imports_and_symbol_imports_are_not_unresolved(self):
        _write(self.root, "pkg/__init__.py")
        _write(self.root, "pkg/a.py", "from . import b\nfrom .b import thing\n")
        _write(self.root, "pkg/b.py", "thing = 1\n")
        result = self.run_impact(["pkg/b.py"])
        self.assertEqual(result["direct_dependents"], ["pkg/a.py"])
        self.assertEqual(result["unresolved_local_references"], [])

    def test_python_missing_relative_module_is_reported_once_with_original_specifier(self):
        _write(self.root, "pkg/__init__.py")
        _write(self.root, "pkg/a.py", "from .missing import q\nfrom .missing import r\n")
        result = self.run_impact(["pkg/a.py"])
        refs = result["unresolved_local_references"]
        self.assertEqual([(r["reference"], r["reason"]) for r in refs], [(".missing", "not_found")])

    def test_python_from_package_import_does_not_create_false_init_cycle(self):
        _write(self.root, "pkg/__init__.py", "from .a import x\n")
        _write(self.root, "pkg/a.py", "from . import b\nx = 1\n")
        _write(self.root, "pkg/b.py", "")
        result = self.run_impact(["pkg/a.py"])
        self.assertFalse(result["possible_dependency_cycle"])

    def test_python_symbol_from_package_init_is_a_dependency(self):
        _write(self.root, "pkg/__init__.py", "VERSION = '1'\n")
        _write(self.root, "pkg/a.py", "from . import VERSION\n")
        result = self.run_impact(["pkg/__init__.py"])
        self.assertIn("pkg/a.py", result["direct_dependents"])

    def test_python_source_root_import_is_inferred_not_confirmed(self):
        _write(self.root, "backend/app/__init__.py")
        _write(self.root, "backend/app/config.py", "X = 1\n")
        _write(self.root, "backend/app/main.py", "from app.config import X\n")
        result = self.run_impact(["backend/app/config.py"])
        self.assertNotIn("backend/app/main.py", result["direct_dependents"])
        self.assertIn("backend/app/main.py", result["possible_dependents"])
        self.assertTrue(any(e["confidence"] == "inferred" for e in result["dependency_edges"]))

    def test_python_ambiguous_source_root_import_makes_no_edge(self):
        _write(self.root, "a/shared/util.py")
        _write(self.root, "b/shared/util.py")
        _write(self.root, "c/use.py", "import shared.util\n")
        result = self.run_impact(["a/shared/util.py"])
        self.assertEqual(result["possible_dependents"], [])
        self.assertEqual(result["direct_dependents"], [])

    def test_python_stdlib_names_never_match_local_files_by_guessing(self):
        _write(self.root, "tools/logging.py")
        _write(self.root, "tools/run.py", "import logging\n")
        result = self.run_impact(["tools/logging.py"])
        self.assertEqual(result["possible_dependents"], [])

    def test_malformed_python_is_reported_as_skipped_not_silent(self):
        _write(self.root, "ok.py", "x = 1\n")
        _write(self.root, "bad.py", "def broken(:\n")
        result = self.run_impact(["ok.py"])
        self.assertIn({"path": "bad.py", "reason": "syntax_error"}, result["skipped_files"])
        self.assertTrue(any("could not be parsed" in item for item in result["limitations"]))

    def test_cycle_report_lists_members(self):
        _write(self.root, "a.py", "import b\n")
        _write(self.root, "b.py", "import c\n")
        _write(self.root, "c.py", "import a\n")
        _write(self.root, "d.py", "import a\n")
        result = self.run_impact(["a.py"])
        self.assertEqual(result["cycles"][0]["files"], ["a.py", "b.py", "c.py"])
        self.assertEqual(result["cycles"][0]["changed_files_involved"], ["a.py"])
        self.assertTrue(result["possible_dependency_cycle"])

    def test_duplicate_imports_produce_one_edge(self):
        _write(self.root, "lib.py")
        _write(self.root, "user.py", "import lib\nimport lib\nfrom lib import x\n")
        result = self.run_impact(["lib.py"])
        edges = [e for e in result["dependency_edges"] if e["importer"] == "user.py"]
        self.assertEqual(len(edges), 1)

    # --- JavaScript / TypeScript ---------------------------------------
    def test_js_index_files_side_effect_dynamic_and_typescript_imports(self):
        _write(self.root, "web/src/utils/index.js", "export const f = 1;\n")
        _write(self.root, "web/src/utils/h.ts", "export const h = 1;\n")
        _write(self.root, "web/src/main.js",
               "import { f } from './utils';\nconst h = import('./utils/h');\n")
        _write(self.root, "web/src/components/index.js", "import '../utils';\n")
        result = self.run_impact(["web/src/utils/index.js"])
        self.assertEqual(result["direct_dependents"], ["web/src/components/index.js", "web/src/main.js"])
        self.assertEqual(result["unresolved_local_references"], [])
        self.assertEqual(self.run_impact(["web/src/utils/h.ts"])["direct_dependents"], ["web/src/main.js"])

    def test_js_comments_and_string_literals_do_not_create_edges(self):
        _write(self.root, "x.js", "export const x = 1;\n")
        _write(self.root, "y.js",
               "// import a from './x'\n/* const b = require('./x') */\nconst s = \"import q from './x'\";\n")
        result = self.run_impact(["x.js"])
        self.assertEqual(result["direct_dependents"], [])

    def test_js_missing_relative_import_reported_once_not_per_extension(self):
        _write(self.root, "a.js", "import './nope';\n")
        result = self.run_impact(["a.js"])
        self.assertEqual(result["unresolved_local_references"],
                         [{"file_path": "a.js", "reference": "./nope", "reason": "not_found"}])

    def test_js_alias_imports_are_inferred_or_listed_as_unmapped_never_confirmed(self):
        _write(self.root, "lib/g.js")
        _write(self.root, "app.js", "import g from '@/lib/g';\nimport z from '@/nowhere/z';\n")
        result = self.run_impact(["lib/g.js"])
        self.assertEqual(result["direct_dependents"], [])
        self.assertEqual(result["possible_dependents"], ["app.js"])
        self.assertEqual(result["unmapped_aliases"], ["@/nowhere/z"])

    def test_js_esm_extension_swap_resolves_ts_source(self):
        _write(self.root, "src/a.ts", "export {};\n")
        _write(self.root, "src/b.ts", "import './a.js';\n")
        self.assertEqual(self.run_impact(["src/a.ts"])["direct_dependents"], ["src/b.ts"])

    # --- Java -----------------------------------------------------------
    def test_java_maven_layout_imports_resolve_by_declared_package(self):
        _write(self.root, "src/main/java/com/acme/util/Helper.java", "package com.acme.util;\npublic class Helper {}\n")
        _write(self.root, "src/main/java/com/acme/app/App.java",
               "package com.acme.app;\nimport com.acme.util.Helper;\nimport java.util.List;\npublic class App {}\n")
        _write(self.root, "src/main/java/com/acme/app/Other.java",
               "package com.acme.app;\nimport static com.acme.util.Helper.run;\npublic class Other {}\n")
        _write(self.root, "src/main/java/com/acme/app/Wild.java",
               "package com.acme.app;\nimport com.acme.util.*;\npublic class Wild {}\n")
        result = self.run_impact(["src/main/java/com/acme/util/Helper.java"])
        self.assertEqual(result["direct_dependents"],
                         ["src/main/java/com/acme/app/App.java", "src/main/java/com/acme/app/Other.java"])
        self.assertEqual(result["possible_dependents"], ["src/main/java/com/acme/app/Wild.java"])
        self.assertEqual(result["unresolved_local_references"], [])

    def test_java_missing_local_class_is_unresolved_but_jdk_is_not(self):
        _write(self.root, "A.java", "package com.acme;\nimport com.acme.Missing;\nimport java.util.Map;\nclass A {}\n")
        refs = self.run_impact(["A.java"])["unresolved_local_references"]
        self.assertEqual([r["reference"] for r in refs], ["com.acme.Missing"])

    # --- tests, paths, limits ------------------------------------------
    def test_related_tests_are_split_into_confirmed_and_name_only(self):
        _write(self.root, "src/helper.py")
        _write(self.root, "tests/test_helper.py", "")  # name match only
        _write(self.root, "tests/test_real.py", "from src import helper\n")
        _write(self.root, "src/latest_utils.py", "from src import helper\n")  # 'test' substring, not a test
        result = self.run_impact(["src/helper.py"])
        self.assertEqual(result["related_tests"], ["tests/test_real.py"])
        self.assertEqual(result["likely_related_tests"], ["tests/test_helper.py"])
        self.assertNotIn("src/latest_utils.py", result["related_tests"] + result["likely_related_tests"])

    def test_windows_style_and_dot_prefixed_changed_paths(self):
        _write(self.root, "pkg/b.py")
        _write(self.root, ".storybook/main.js", "export {};\n")
        self.assertEqual(self.run_impact(["pkg\\b.py"])["changed_files"], ["pkg/b.py"])
        self.assertEqual(self.run_impact([".\\pkg\\b.py"])["changed_files"], ["pkg/b.py"])
        self.assertEqual(self.run_impact([".storybook/main.js"])["changed_files"], [".storybook/main.js"])

    def test_case_only_difference_is_accepted_when_unambiguous(self):
        _write(self.root, "Pkg/Mod.py")
        self.assertEqual(self.run_impact(["pkg/mod.py"])["changed_files"], ["Pkg/Mod.py"])

    def test_invalid_changed_paths_are_rejected(self):
        _write(self.root, "a.py")
        for bad in ("../a.py", "x/../../a.py", "/etc/passwd", "C:\\Windows\\x.py", "C:/x.py", "", "  ", "a\x00.py"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.run_impact([bad])
        with self.assertRaises(ValueError):
            self.run_impact([123])

    def test_unsupported_changed_file_type_is_rejected_with_explanation(self):
        _write(self.root, "a.py")
        _write(self.root, "photo.png", "x")
        with self.assertRaises(ValueError) as caught:
            self.run_impact(["photo.png"])
        self.assertIn("unsupported file types", str(caught.exception))

    def test_non_code_changed_file_adds_limitation_note(self):
        _write(self.root, "styles.css", "a{}")
        _write(self.root, "a.js", "import './styles.css';\n")
        result = self.run_impact(["styles.css"])
        self.assertEqual(result["direct_dependents"], ["a.js"])
        self.assertTrue(any("non-code changed files" in item for item in result["limitations"]))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinked_files_are_never_read(self):
        outside = tempfile.TemporaryDirectory()
        try:
            _write(outside.name, "secret.py", "import a\n")
            _write(self.root, "a.py")
            try:
                os.symlink(Path(outside.name) / "secret.py", self.root / "link.py")
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation not permitted")
            result = self.run_impact(["a.py"])
            self.assertNotIn("link.py", result["direct_dependents"])
            self.assertNotIn("link.py", result["possible_dependents"])
        finally:
            outside.cleanup()

    def test_file_cap_reads_changed_file_and_its_neighbours_first_and_reports_truncation(self):
        _write(self.root, "zz/lib.py")
        _write(self.root, "zz/user.py", "from zz import lib\n")
        for i in range(120):
            _write(self.root, f"aa/m{i:03}.py", "x = 1\n")
        with patch.dict(os.environ, {"RAG_IMPACT_MAX_FILES": "100"}):
            result = self.run_impact(["zz/lib.py"])
        self.assertIn("zz/user.py", result["direct_dependents"])
        self.assertTrue(result["truncated"])
        self.assertTrue(any("file cap" in item for item in result["limitations"]))

    def test_oversized_files_are_listed_as_skipped(self):
        _write(self.root, "a.py", "x = 1\n")
        _write(self.root, "big.py", "x = 1\n" * 3000)
        with patch.dict(os.environ, {"RAG_IMPACT_MAX_FILE_BYTES": "10000"}):
            result = self.run_impact(["a.py"])
        self.assertIn({"path": "big.py", "reason": "too_large"}, result["skipped_files"])

    def test_result_never_contains_source_text(self):
        _write(self.root, "a.py", "SECRET_MARKER = 'do-not-leak'\n")
        _write(self.root, "b.py", "import a\n")
        self.assertNotIn("do-not-leak", repr(self.run_impact(["a.py"])))
