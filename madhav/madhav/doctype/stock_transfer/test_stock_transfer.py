# Copyright (c) 2026, Finbyz pvt. ltd. and Contributors
# See license.txt

"""Stock Transfer cancel rollback tests.

Run via:
  bench --site madhav.localhost run-tests --app madhav --module madhav.madhav.doctype.stock_transfer.test_stock_transfer
"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from madhav.madhav.doctype.stock_transfer.stock_transfer import (
	StockTransfer,
	_cancel_psles_for_voucher,
)


class TestStockTransferCancelHelpers(FrappeTestCase):
	"""Unit-style tests for cancel rollback helpers."""

	def test_cancel_psles_skips_empty_voucher(self):
		with patch("madhav.madhav.doctype.stock_transfer.stock_transfer.frappe.get_all") as get_all:
			_cancel_psles_for_voucher("")
			get_all.assert_not_called()

	def test_cancel_psles_cancels_each_doc(self):
		psle = MagicMock()
		with patch(
			"madhav.madhav.doctype.stock_transfer.stock_transfer.frappe.get_all",
			return_value=["PSLE-1", "PSLE-2"],
		), patch(
			"madhav.madhav.doctype.stock_transfer.stock_transfer.frappe.get_doc",
			return_value=psle,
		):
			_cancel_psles_for_voucher("MAT-STE-1")
			self.assertEqual(psle.cancel.call_count, 2)
			self.assertTrue(psle.flags.ignore_links)

	def test_resolve_prefers_stock_entry_field(self):
		doc = frappe.get_doc(
			{
				"doctype": "Stock Transfer",
				"stock_entry": "SE-1",
			}
		)
		doc.name = "STE-1"
		with patch(
			"madhav.madhav.doctype.stock_transfer.stock_transfer.frappe.db.exists",
			return_value=True,
		):
			self.assertEqual(doc._resolve_linked_stock_entry(), "SE-1")

	def test_on_cancel_cancels_sre_then_se_with_ignore_links(self):
		doc = frappe.get_doc({"doctype": "Stock Transfer"})
		doc.name = "STE-X"
		doc.stock_entry = "SE-X"
		doc.transfer_item = []

		sre = MagicMock()
		se = MagicMock()
		se.docstatus = 1

		with patch.object(doc, "_resolve_linked_stock_entry", return_value="SE-X"), patch(
			"madhav.madhav.doctype.stock_transfer.stock_transfer._cancel_psles_for_voucher"
		) as cancel_psle, patch(
			"madhav.madhav.doctype.stock_transfer.stock_transfer.frappe.get_all",
			return_value=["SRE-1"],
		), patch(
			"madhav.madhav.doctype.stock_transfer.stock_transfer.frappe.get_doc",
			side_effect=[sre, se],
		), patch.object(doc, "db_set"):
			doc.on_cancel()

			sre.cancel.assert_called_once()
			cancel_psle.assert_called_once_with("SE-X")
			self.assertTrue(se.flags.ignore_links)
			se.cancel.assert_called_once()

	def test_on_cancel_throws_when_stock_entry_missing(self):
		doc = frappe.get_doc({"doctype": "Stock Transfer"})
		doc.name = "STE-MISSING"
		doc.stock_entry = None
		doc.append(
			"transfer_item",
			{
				"item_code": "TEST-ITEM",
				"qty": 1,
				"batch": "BATCH-1",
			},
		)

		with patch.object(doc, "_resolve_linked_stock_entry", return_value=None), patch(
			"madhav.madhav.doctype.stock_transfer.stock_transfer.frappe.get_all",
			return_value=[],
		), patch.object(doc, "db_set"):
			self.assertRaises(Exception, doc.on_cancel)


class TestStockTransferResolveIntegration(FrappeTestCase):
	"""Live-site checks for known broken docs (read-only resolve)."""

	def test_resolve_finds_orphaned_se_for_ste_0229(self):
		"""STE-26-0229 submitted with blank stock_entry; SE MAT-STE-00009 exists."""
		if not frappe.db.exists("Stock Transfer", "STE-26-0229"):
			self.skipTest("STE-26-0229 not on this site")

		doc = frappe.get_doc("Stock Transfer", "STE-26-0229")
		if doc.stock_entry:
			self.skipTest("STE-26-0229 already has stock_entry linked")

		se_name = doc._resolve_linked_stock_entry()
		self.assertTrue(se_name, "Should find Material Transfer via batch fallback")
		se = frappe.get_doc("Stock Entry", se_name)
		self.assertEqual(se.from_warehouse, doc.source_warehouse)
		self.assertEqual(se.to_warehouse, doc.target_warehouse)
		self.assertEqual(se.stock_entry_type, "Material Transfer")
