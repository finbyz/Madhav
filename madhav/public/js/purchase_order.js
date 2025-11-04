frappe.ui.form.on("Purchase Order Item", {

    // item_code: function(frm, cdt, cdn) {
    //     const rm_item_groups = [
    //         "ALL ITEM GROUP", "BLOOM", "BILLET", "RM ANGLE",
    //         "BEAM", "PLATES", "CHANNEL"
    //     ];

    //     const store_spares_groups = [
    //         "DIE & BUSHES", "DISC", "ELECTRICAL", "FABRICATION CONSUMABLES",
    //         "FURNACE", "GAS", "GAS CUTTING & ACCESSORIES", "GUN METALS & BRONZE",
    //         "HAND TOOLS", "HYDRA EXPENSES", "LASER & PLASMA ACCESSORIES",
    //         "MECHANICAL ITEMS", "OIL & GREASES", "PACKING & BUNDLING", "ROLL",
    //         "SAFETY MATERIAL", "SHAFT", "SPARES", "WELDING & ACCESSORIES"
    //     ];

    //     const allowed_groups = [...rm_item_groups, ...store_spares_groups];

    //     // Apply filter to show only allowed item groups
    //     frm.fields_dict.items.grid.get_field("item_code").get_query = function() {
    //         return {
    //             filters: {
    //                 item_group: ["in", allowed_groups]
    //             }
    //         };
    //     };
    // },

    item_code: function(frm, cdt, cdn) {
        const row = frappe.get_doc(cdt, cdn);

        const rm_item_groups = [
            "ALL ITEM GROUP", "BLOOM", "BILLET", "RM ANGLE",
            "BEAM", "PLATES", "CHANNEL"
        ];

        const store_spares_groups = [
            "DIE & BUSHES", "DISC", "ELECTRICAL", "FABRICATION CONSUMABLES",
            "FURNACE", "GAS", "GAS CUTTING & ACCESSORIES", "GUN METALS & BRONZE",
            "HAND TOOLS", "HYDRA EXPENSES", "LASER & PLASMA ACCESSORIES",
            "MECHANICAL ITEMS", "OIL & GREASES", "PACKING & BUNDLING", "ROLL",
            "SAFETY MATERIAL", "SHAFT", "SPARES", "WELDING & ACCESSORIES"
        ];

        if (row.item_code) {
            frappe.db.get_value("Item", row.item_code, "item_group", (r) => {
                if (!r || !r.item_group) return;

                // Check if item belongs to RM or Store & Spares group
                if (
                    rm_item_groups.includes(r.item_group) ||
                    store_spares_groups.includes(r.item_group)
                ) {
                    frappe.call({
                        method: "madhav.api.get_material_request_for_item",
                        args: { item_code: row.item_code },
                        callback: function(res) {
                            if (!res.message) {
                                frappe.msgprint({
                                    title: __("Material Request Required"),
                                    message: __(
                                        "Material Request not found for item: <b>{0}</b> (Group: <b>{1}</b>)",
                                        [row.item_code, r.item_group]
                                    ),
                                    indicator: "red"
                                });

                                //  Clear the row fields
                                frappe.model.clear_doc(cdt, cdn);
                                frm.refresh_field("items");
                            } else {
                                console.log("Material Request Found:", res.message.parent);
                            }
                        }
                    });
                }
            });
        }
    }
});
