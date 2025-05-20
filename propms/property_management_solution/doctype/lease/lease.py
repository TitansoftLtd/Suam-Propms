# -*- coding: utf-8 -*-
# Copyright (c) 2018, Aakvatech and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
from frappe.utils import add_days, today, getdate, add_months, get_datetime, now
from propms.auto_custom import app_error_log, makeInvoiceSchedule, getDateMonthDiff


class Lease(Document):
    def on_submit(self):
        try:
            checklist_doc = frappe.get_doc("Checklist Checkup Area", "Handover")
            if checklist_doc:
                check_list = []
                for task in checklist_doc.task:
                    check = {}
                    check["checklist_task"] = task.task_name
                    check_list.append(check)

                frappe.get_doc(
                    dict(
                        doctype="Daily Checklist",
                        area="Handover",
                        checkup_date=self.start_date,
                        daily_checklist_detail=check_list,
                        property=self.property,
                    )
                ).insert()
        except Exception as e:
            app_error_log(frappe.session.user, str(e))

    def validate(self):
        try:
            if (
                get_datetime(self.start_date)
                <= get_datetime(now())
                <= get_datetime(add_months(self.end_date, -3))
            ):
                frappe.db.set_value("Property", self.property, "status", "On Lease")
                frappe.msgprint("Property set to On Lease")
            if (
                get_datetime(add_months(self.end_date, -3))
                <= get_datetime(now())
                <= get_datetime(add_months(self.end_date, 3))
            ):
                frappe.db.set_value(
                    "Property", self.property, "status", "Off Lease in 3 Months"
                )
                frappe.msgprint("Property set to Off Lease in 3 Months")
        except Exception as e:
            app_error_log(frappe.session.user, str(e))


@frappe.whitelist()
def getAllLease():
    # Below is temporarily created to manually run through all lease and refresh lease invoice schedule. Hardcoded to start from 1st Jan 2020.
    frappe.msgprint(
        "The task of making lease invoice schedule for all users has been sent for background processing."
    )
    invoice_start_date = frappe.db.get_single_value(
        "Property Management Settings", "invoice_start_date"
    )
    lease_list = frappe.get_all(
        "Lease", filters={"end_date": (">=", invoice_start_date)}, fields=["name"]
    )
    # frappe.msgprint("Working on lease_list" + str(lease_list))
    lease_list_len = len(lease_list)
    frappe.msgprint("Total number of lease to be processed is " + str(lease_list_len))
    for lease in lease_list:
        make_lease_invoice_schedule(lease.name)


@frappe.whitelist()
def make_lease_invoice_schedule(leasedoc):
    try:
        lease = frappe.get_doc("Lease", str(leasedoc))

        def delete_unnecessary_schedules():
            # Delete schedules after lease end date
            future_schedules = frappe.get_list(
                "Lease Invoice Schedule",
                filters={"parent": lease.name, "date_to_invoice": (">", lease.end_date)},
                pluck="name"
            )
            for name in future_schedules:
                frappe.delete_doc("Lease Invoice Schedule", name)

            # Delete schedules before invoice_start_date
            invoice_start_date = frappe.db.get_single_value("Property Management Settings", "invoice_start_date")
            past_schedules = frappe.get_list(
                "Lease Invoice Schedule",
                filters={"parent": lease.name, "date_to_invoice": ("<", invoice_start_date)},
                pluck="name"
            )
            for name in past_schedules:
                frappe.delete_doc("Lease Invoice Schedule", name)

        def delete_stale_lease_items():
            valid_lease_items = frappe.get_list(
                "Lease Item", filters={"parent": lease.name}, pluck="lease_item"
            )
            all_schedules = frappe.get_list(
                "Lease Invoice Schedule",
                filters={"parent": lease.name},
                fields=["name", "lease_item"]
            )
            for sched in all_schedules:
                if sched.lease_item not in valid_lease_items:
                    frappe.delete_doc("Lease Invoice Schedule", sched.name)

        def process_invoice_schedules():
            item_invoice_frequency = {
                "Monthly": 1.0,
                "Bi-Monthly": 2.0,
                "Quarterly": 3.0,
                "6 months": 6.0,
                "Annually": 12.0,
            }

            idx = 1
            invoice_start_date = frappe.db.get_single_value("Property Management Settings", "invoice_start_date")

            for item in lease.lease_item:
                freq = item_invoice_frequency.get(item.frequency)
                if not freq:
                    message = f"Invalid frequency: {item.frequency} for {lease.name}. Contact the developers!"
                    frappe.log_error("Frequency incorrect", message)
                    continue

                # Ensure lease_item has valid start and end dates
                if not item.start_date or not item.end_date:
                    frappe.log_error("Missing Dates", f"Start or End Date missing in Lease Item: {item.name}")
                    continue

                # Use item-level start and end dates
                invoice_date = item.start_date
                end_date = item.end_date

                # Move invoice_date past any global invoice start limit
                while end_date >= invoice_date and invoice_date < invoice_start_date:
                    invoice_date = add_days(add_months(invoice_date, freq), 0)

                existing_schedules = frappe.get_all(
                    "Lease Invoice Schedule",
                    filters={"parent": lease.name, "lease_item": item.name},
                    fields=["name", "invoice_number", "qty", "schedule_start_date", "date_to_invoice"],
                    order_by="date_to_invoice"
                )

                if not existing_schedules:
                    while end_date >= invoice_date:
                        period_end = add_days(add_months(invoice_date, freq), -1)
                        qty = getDateMonthDiff(invoice_date, min(period_end, end_date), 1)

                        makeInvoiceSchedule(
                            invoice_date, item.lease_item, item.paid_by, item.lease_item,
                            lease.name, qty, item.invoice_amount, idx, item.currency_code,
                            item.witholding_tax, lease.days_to_invoice_in_advance,
                            item.invoice_item_group, item.document_type
                        )

                        idx += 1
                        invoice_date = add_days(period_end, 1)
                else:
                    for sched in existing_schedules:
                        if sched.invoice_number:
                            months_to_add = round(sched.qty)
                            if sched.qty != months_to_add:
                                months_to_add += 1

                            invoice_date = add_months(sched.schedule_start_date or sched.date_to_invoice, months_to_add)
                            frappe.db.set_value("Lease Invoice Schedule", sched.name, "idx", idx)
                            idx += 1
                        else:
                            frappe.delete_doc("Lease Invoice Schedule", sched.name)

                    # Continue creating new schedules after last one
                    while end_date >= invoice_date:
                        period_end = add_days(add_months(invoice_date, freq), -1)
                        qty = getDateMonthDiff(invoice_date, min(period_end, end_date), 1)

                        makeInvoiceSchedule(
                            invoice_date, item.lease_item, item.paid_by, item.lease_item,
                            lease.name, qty, item.invoice_amount, idx, item.currency_code,
                            item.witholding_tax, lease.days_to_invoice_in_advance,
                            item.invoice_item_group, item.document_type
                        )

                        idx += 1
                        invoice_date = add_days(period_end, 1)


        # Only run for leases with items and active
        if lease.lease_item and lease.end_date >= getdate(today()):
            delete_unnecessary_schedules()
            delete_stale_lease_items()
            process_invoice_schedules()

        frappe.msgprint("Completed making of invoice schedule.")

    except Exception as e:
        frappe.log_error(title="make_lease_invoice_schedule error", message=frappe.get_traceback())
        frappe.msgprint("An error occurred. Please check the error log.")
