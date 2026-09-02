import unittest

from madhav.madhav.utils.stock_piece_utils import (
	_entry_avail_qty,
	resolve_entry_pieces,
	resolve_weighted_length_from_entries,
	sum_undelivered_pieces_from_sre_rows,
)


class TestStockPieceUtilsPartialDelivery(unittest.TestCase):
	def test_entry_avail_qty_excludes_fully_delivered_sre_row(self):
		row = {"qty": 0.5, "delivered_qty": 0.5}
		self.assertEqual(_entry_avail_qty(row), 0)

	def test_entry_avail_qty_uses_undelivered_share(self):
		row = {"qty": 0.5, "delivered_qty": 0.2}
		self.assertAlmostEqual(_entry_avail_qty(row), 0.3)

	def test_entry_avail_qty_for_outward_bundle_row(self):
		row = {"qty": -0.445, "delivered_qty": 0}
		self.assertAlmostEqual(_entry_avail_qty(row), 0.445)

	def test_weighted_length_skips_fully_delivered_batch(self):
		entries = [
			{"qty": 0.4, "delivered_qty": 0.4, "length": 6.0, "batch_no": "B1"},
			{"qty": 0.3, "delivered_qty": 0.0, "length": 8.5, "batch_no": "B2"},
		]
		self.assertAlmostEqual(resolve_weighted_length_from_entries(entries), 8.5)

	def test_weighted_length_multi_batch_undelivered_only(self):
		entries = [
			{"qty": 0.4, "delivered_qty": 0.1, "length": 6.0, "batch_no": "B1"},
			{"qty": 0.3, "delivered_qty": 0.0, "length": 8.5, "batch_no": "B2"},
		]
		# (0.3 * 6 + 0.3 * 8.5) / 0.6 = 7.25
		self.assertAlmostEqual(resolve_weighted_length_from_entries(entries), 7.25)

	def test_resolve_entry_pieces_scales_stored_pieces_for_partial_delivery(self):
		row = {
			"qty": 0.5,
			"delivered_qty": 0.2,
			"pieces": 10,
			"length": 6.0,
			"section_weight": 9.0,
		}
		avail = 0.3
		# proportional: round(10 * 0.3 / 0.3) = 10, but orig avail is 0.3 from 0.5 total
		# stored 10 for 0.5 qty, avail 0.3 -> round(10 * 0.3/0.3) wait orig_avail = 0.5-0.2=0.3, avail=0.3
		# full stored pieces since all undelivered
		self.assertEqual(resolve_entry_pieces(row, avail, 6.0, 9.0), 10)

		row2 = {
			"qty": 0.5,
			"delivered_qty": 0.0,
			"pieces": 10,
			"length": 6.0,
			"section_weight": 9.0,
		}
		self.assertEqual(resolve_entry_pieces(row2, 0.25, 6.0, 9.0), 5)

	def test_sum_undelivered_pieces_skips_fully_delivered_batch(self):
		rows = [
			{
				"batch_no": "B1",
				"qty": 0.4,
				"delivered_qty": 0.4,
				"pieces": 8,
				"length": 6.0,
				"section_weight": 9.0,
			},
			{
				"batch_no": "B2",
				"qty": 0.3,
				"delivered_qty": 0.0,
				"pieces": 6,
				"length": 8.5,
				"section_weight": 9.0,
			},
		]
		self.assertEqual(sum_undelivered_pieces_from_sre_rows(rows), 6)


if __name__ == "__main__":
	unittest.main()
