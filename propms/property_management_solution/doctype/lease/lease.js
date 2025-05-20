// Copyright (c) 2018, Aakvatech and contributors
// For license information, please see license.txt
cur_frm.add_fetch('property', 'unit_owner', 'property_owner');

frappe.ui.form.on('Lease', {
	setup: function(frm) {
		frm.set_query("lease_item", "lease_item", function() {
			return {
				"filters": [
                    ["item_group","=", "Lease Items"],
				]
			};
		});
		frm.set_query("property", function() {
			return {
				"filters": {
                    "company": frm.doc.company,
				},
			};
		});
	},
	refresh: function(frm) {
		cur_frm.add_custom_button(__("Make Invoice Schedule"), function() {
			make_lease_invoice_schedule(cur_frm);
		});
		cur_frm.add_custom_button(__("Generate Pending Invoice"), function() {
			generate_pending_invoice();
		});
		cur_frm.add_custom_button(__("Make Invoice Schedule for all Lease"), function() {
			getAllLease(cur_frm);
		});
	},
	onload: function(frm) {
			frappe.realtime.on("lease_invoice_schedule_progress", function(data) {
			if (data.reload && data.reload === 1) {
				frm.reload_doc();
			}
			if (data.progress) {
				let progress_bar = $(cur_frm.dashboard.progress_area).find(".progress-bar");
				if (progress_bar) {
					$(progress_bar).removeClass("progress-bar-danger").addClass("progress-bar-success progress-bar-striped");
					$(progress_bar).css("width", data.progress+"%");
				}
			}
		});
	},
	lease_customer: function (frm) {
        // Update existing child rows when lease_customer is changed
        (frm.doc.lease_item || []).forEach(function (d) {
            d.paid_by = frm.doc.lease_customer;
        });
        frm.refresh_field('lease_item');
    },

    lease_item_add: function (frm, cdt, cdn) {
        // Set paid_by on a newly added row
        if (frm.doc.lease_customer) {
            frappe.model.set_value(cdt, cdn, 'paid_by', frm.doc.lease_customer);
        }
    }
});

frappe.ui.form.on('Lease Item', {
    amount: function(frm, cdt, cdn) {
        update_invoice_amount(frm, cdt, cdn);
    },
    increment: function(frm, cdt, cdn) {
        update_invoice_amount(frm, cdt, cdn);
    }
});

function update_invoice_amount(frm, cdt, cdn) {
    var row = locals[cdt][cdn];
    if (row.amount && row.increment != null) {
        row.invoice_amount = row.amount + (row.amount * row.increment / 100);
        frm.refresh_field('lease_item');
    }
}

var make_lease_invoice_schedule = function(frm){
	var doc = frm.doc;
	frappe.call({
		method: "propms.property_management_solution.doctype.lease.lease.make_lease_invoice_schedule",
		args: {leasedoc: doc.name},
		callback: function(){
			cur_frm.reload_doc();
		}
	});
};

var generate_pending_invoice = function(){
	frappe.call({
		method: "propms.lease_invoice.leaseInvoiceAutoCreate",
		args: {},
		callback: function(){
			cur_frm.reload_doc();
		}
	});
};

var getAllLease = function(){
	frappe.confirm(
		'Are you sure to initiate this long process?',
		function(){
			frappe.call({
				method: "propms.property_management_solution.doctype.lease.lease.getAllLease",
				args: {},
				callback: function(){
					cur_frm.reload_doc();
				}
			});
		},
		function(){
			frappe.msgprint(__("Closed before starting long process!"));
			window.close();
		}
	)
};