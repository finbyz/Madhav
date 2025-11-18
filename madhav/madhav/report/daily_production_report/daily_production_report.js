// Copyright (c) 2025, Finbyz pvt. ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Daily Production Report"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		// {
		// 	"fieldname": "company",
		// 	"label": __("Company"),
		// 	"fieldtype": "Link",
		// 	"options": "Company"
		// },
		// {
		// 	"fieldname": "workflow_state",
		// 	"label": __("Workflow State"),
		// 	"fieldtype": "Link",
		// 	"options": "Workflow State"
		// },
		// {
		// 	"fieldname": "item",
		// 	"label": __("Item"),
		// 	"fieldtype": "Link",
		// 	"options": "Item"
		// },
		// {
		// 	"fieldname": "warehouse",
		// 	"label": __("Warehouse"),
		// 	"fieldtype": "Link",
		// 	"options": "Warehouse"
		// },
		// {
		// 	"fieldname": "return_to_stock",
		// 	"label": __("Return to Stock"),
		// 	"fieldtype": "Check"
		// },
		// {
		// 	"fieldname": "work_order",
		// 	"label": __("Work Order"),
		// 	"fieldtype": "Link",
		// 	"options": "Work Order"
		// }
	],

	formatter: function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (data && data.is_total_row) {
			value = `
				<span style="
					font-weight: 600;
					background-color: #ffda03;
					display: block;
					padding: 4px 6px;
					border-radius: 2px;
				">
					${value}
				</span>`;
		}

		return value;
	},

	onload: function(report) {
		report.page.add_inner_button(__('Refresh'), function() {
			report.refresh();
		});
	},

	after_datatable_render: function(datatable_instance) {
		add_column_group_headers(datatable_instance);
	}
};

function add_column_group_headers(datatable) {
	try {
		// Remove any existing group headers
		const existing = datatable.wrapper.querySelectorAll('.custom-column-group-header');
		existing.forEach(el => el.remove());

		// Get the header row container
		const headerRow = datatable.wrapper.querySelector('.dt-header .dt-row');
		if (!headerRow) return;

		// Get all header cells
		const headerCells = Array.from(headerRow.querySelectorAll('.dt-cell'));
		if (headerCells.length === 0) return;

		// Log column information for debugging
		console.log('Total header cells:', headerCells.length);
		
		// Find columns by their text content instead of relying on fixed indices
		const columnIndices = {};
		headerCells.forEach((cell, index) => {
			const cellText = cell.textContent.trim();
			columnIndices[cellText] = index;
			console.log(`Column ${index}: "${cellText}"`);
		});

		// Determine column groups dynamically based on actual column names
		let rmScrapStart = columnIndices['R.M Scrap'];
		let missRollIdx = columnIndices['MISS ROLL (MT)'];
		let endCutIdx = columnIndices['END CUT (MT)'];
		let inspYardIdx = columnIndices['INSP + YARD (MT)'];

		const columnGroups = [];
		
		// R.M Scrap group: R.M Scrap, MISS ROLL, END CUT (3 columns)
		if (rmScrapStart !== undefined && endCutIdx !== undefined) {
			columnGroups.push({
				startIndex: rmScrapStart,
				endIndex: endCutIdx,
				label: 'R.M Scrap',
				bgColor: '#FFC7CE',
				textColor: '#000'
			});
		}
		
		// FG SCRAP group: INSP + YARD only (1 column)
		if (inspYardIdx !== undefined) {
			columnGroups.push({
				startIndex: inspYardIdx,
				endIndex: inspYardIdx,
				label: 'FG SCRAP',
				bgColor: '#C6EFCE',
				textColor: '#000'
			});
		}

		console.log('Column groups:', JSON.stringify(columnGroups, null, 2));

		// Create group header row
		const groupHeaderRow = document.createElement('div');
		groupHeaderRow.className = 'dt-row custom-column-group-header';
		groupHeaderRow.style.cssText = `
			display: flex;
			border-bottom: 1px solid #d1d8dd;
			background-color: #f5f7fa;
			position: relative;
		`;

		// Create cells for each position
		let currentCol = 0;
		
		headerCells.forEach((cell, index) => {
			const cellWidth = cell.offsetWidth || parseFloat(cell.style.width) || 100;
			
			// Check if this column is part of a group
			let groupInfo = null;
			for (const group of columnGroups) {
				if (index >= group.startIndex && index <= group.endIndex) {
					groupInfo = group;
					break;
				}
			}

			// If it's the start of a group, create a spanning cell
			if (groupInfo && index === groupInfo.startIndex) {
				// Calculate total width for the group
				let totalWidth = 0;
				for (let i = groupInfo.startIndex; i <= groupInfo.endIndex && i < headerCells.length; i++) {
					totalWidth += headerCells[i].offsetWidth || parseFloat(headerCells[i].style.width) || 100;
				}

				const groupCell = document.createElement('div');
				groupCell.className = 'dt-cell group-header-cell';
				groupCell.style.cssText = `
					width: ${totalWidth}px;
					min-width: ${totalWidth}px;
					max-width: ${totalWidth}px;
					padding: 6px 4px;
					text-align: center;
					font-weight: 600;
					font-size: 11px;
					background-color: ${groupInfo.bgColor};
					color: ${groupInfo.textColor};
					border-right: 1px solid #d1d8dd;
					display: flex;
					align-items: center;
					justify-content: center;
					box-sizing: border-box;
				`;
				groupCell.textContent = groupInfo.label;
				groupHeaderRow.appendChild(groupCell);
			} 
			// If it's a middle column of a group, skip it
			else if (groupInfo && index > groupInfo.startIndex && index <= groupInfo.endIndex) {
				// Skip - this column is covered by the group header
			}
			// Otherwise create an empty cell
			else {
				const emptyCell = document.createElement('div');
				emptyCell.className = 'dt-cell';
				emptyCell.style.cssText = `
					width: ${cellWidth}px;
					min-width: ${cellWidth}px;
					max-width: ${cellWidth}px;
					padding: 6px 4px;
					border-right: 1px solid #d1d8dd;
					box-sizing: border-box;
				`;
				emptyCell.innerHTML = '&nbsp;';
				groupHeaderRow.appendChild(emptyCell);
			}
		});

		// Insert the group header row above the regular header
		const headerContainer = headerRow.parentElement;
		headerContainer.insertBefore(groupHeaderRow, headerRow);

		// Add custom styles
		if (!document.getElementById('daily-production-report-styles')) {
			const style = document.createElement('style');
			style.id = 'daily-production-report-styles';
			style.textContent = `
				.custom-column-group-header {
					min-height: 30px;
				}
				.custom-column-group-header .group-header-cell {
					font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
				}
			`;
			document.head.appendChild(style);
		}

	} catch (error) {
		console.error('Error adding column group headers:', error);
	}
}