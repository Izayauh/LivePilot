import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from livepilot_tools.kontakt_library import filter_favorites, list_kontakt_favorites


class KontaktLibraryTests(unittest.TestCase):
    def test_list_kontakt_favorites_joins_shared_favorites_to_kontakt_sounds(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            favorites_db = root / "favorites.db3"
            kontakt_db = root / "komplete.db3"
            piano_path = root / "Ultra Soft Grand.nksn"
            piano_path.write_text("snapshot", encoding="utf-8")

            self._make_favorites_db(favorites_db)
            self._make_kontakt_db(kontakt_db, str(piano_path))

            result = list_kontakt_favorites(favorites_db=favorites_db, kontakt_db=kontakt_db)

            self.assertTrue(result["success"])
            self.assertEqual(result["favoriteIdCount"], 2)
            self.assertEqual(len(result["favorites"]), 1)
            favorite = result["favorites"][0]
            self.assertEqual(favorite["name"], "Ultra Soft Grand")
            self.assertEqual(favorite["product"], "The Grandeur")
            self.assertEqual(favorite["file_ext"], "nksn")
            self.assertTrue(favorite["load_candidate"])
            self.assertTrue(favorite["path_exists"])
            self.assertIn("piano", favorite["roles"])
            self.assertIn("The Grandeur: Ultra Soft Grand", result["roleGroups"]["piano"])

    def test_filter_favorites_uses_roles_and_text(self):
        favorites = [
            {"name": "Ultra Soft Grand", "product": "The Grandeur", "roles": ["piano"], "categories": []},
            {"name": "MTown Legato", "product": "Session Strings", "roles": ["strings"], "categories": []},
        ]

        matches = filter_favorites(favorites, role="piano", text="grandeur")

        self.assertEqual([item["name"] for item in matches], ["Ultra Soft Grand"])

    def _make_favorites_db(self, path):
        con = sqlite3.connect(path)
        con.execute("create table favorites (id text)")
        con.executemany("insert into favorites values (?)", [("fav-piano",), ("missing-fav",)])
        con.commit()
        con.close()

    def _make_kontakt_db(self, path, piano_path):
        con = sqlite3.connect(path)
        con.executescript(
            """
            create table k_sound_info (
                id integer,
                name text,
                vendor text,
                file_name text,
                file_ext text,
                favorite_id text,
                bank_chain_id integer,
                content_path_id integer
            );
            create table k_bank_chain (
                id integer,
                entry1 text,
                entry2 text,
                entry3 text
            );
            create table k_content_path (
                id integer,
                alias text,
                path text
            );
            create table k_category (
                id integer,
                category text,
                subcategory text,
                subsubcategory text
            );
            create table k_sound_info_category (
                sound_info_id integer,
                category_id integer
            );
            create table k_mode (
                id integer,
                name text
            );
            create table k_sound_info_mode (
                sound_info_id integer,
                mode_id integer
            );
            """
        )
        con.execute(
            "insert into k_sound_info values (1, 'Ultra Soft Grand', 'Native Instruments', ?, 'nksn', 'fav-piano', 10, 20)",
            (piano_path,),
        )
        con.execute("insert into k_bank_chain values (10, 'The Grandeur', null, null)")
        con.execute("insert into k_content_path values (20, 'The Grandeur', ?)", (str(Path(piano_path).parent),))
        con.execute("insert into k_category values (30, 'Piano / Keys', 'Grand Piano', null)")
        con.execute("insert into k_sound_info_category values (1, 30)")
        con.execute("insert into k_mode values (40, 'Sample-based')")
        con.execute("insert into k_sound_info_mode values (1, 40)")
        con.commit()
        con.close()


if __name__ == "__main__":
    unittest.main()
