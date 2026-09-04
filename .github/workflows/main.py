import csv
from datetime import datetime
import os
import sqlite3
import flet as ft

DB_NAME = "machine_management.db"


def init_db():
    """Create Database and Tables with Automatic Schema Migration"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_name TEXT NOT NULL,
            machine_type TEXT,
            machine_no TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            machine_id INTEGER,
            machine_name TEXT NOT NULL,
            machine_type TEXT,
            machine_no TEXT,
            start_time TEXT,
            end_time TEXT,
            work_hours REAL NOT NULL,
            fuel_gallons REAL DEFAULT 0,
            remark TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS machine_status (
            date TEXT,
            machine_id INTEGER,
            status TEXT,
            PRIMARY KEY (date, machine_id)
        )
    """)

    # --- Database Migration Check ---
    cursor.execute("PRAGMA table_info(records)")
    columns = [col[1] for col in cursor.fetchall()]

    if "fuel_liters" in columns and "fuel_gallons" not in columns:
        cursor.execute("ALTER TABLE records RENAME COLUMN fuel_liters TO fuel_gallons")
    elif "fuel_gallons" not in columns:
        cursor.execute("ALTER TABLE records ADD COLUMN fuel_gallons REAL DEFAULT 0")

    conn.commit()
    conn.close()


def parse_time_string(time_str):
    if not time_str:
        return None
    time_str = time_str.strip()
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%I:%M"):
        try:
            dt = datetime.strptime(time_str, fmt)
            now = datetime.now()
            return datetime(now.year, now.month, now.day, dt.hour, dt.minute)
        except ValueError:
            pass
    return None


def parse_date_string(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def get_download_path():
    """Android / Storage Path Detection"""
    android_download_path = "/storage/emulated/0/Download"
    if os.path.exists(android_download_path):
        return android_download_path

    # Desktop (Windows / Mac / Linux) Fallback
    user_download_path = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.exists(user_download_path):
        return user_download_path

    return os.getcwd()


def main(page: ft.Page):
    page.title = "Machine Hours and Fuel Record Management"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 15
    page.scroll = ft.ScrollMode.AUTO

    # Font Setup
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    font_path = os.path.join(assets_dir, "Pyidaungsu-2.5_Regular.ttf")
    if os.path.exists(font_path):
        page.fonts = {"Pyidaungsu": "assets/Pyidaungsu-2.5_Regular.ttf"}
        page.theme = ft.Theme(font_family="Pyidaungsu")

    init_db()

    def show_snack(msg: str, color=ft.colors.GREEN_700):
        snack = ft.SnackBar(ft.Text(msg, color=ft.colors.WHITE), bgcolor=color)
        page.overlay.append(snack)
        snack.open = True
        page.update()

    # ==========================================
    # EXPORT CSV LOGIC
    # ==========================================
    def export_daily_csv(e):
        try:
            target_dir = get_download_path()
            file_name = f"daily_machine_details_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            save_path = os.path.join(target_dir, file_name)

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            order_clause = "ASC" if rec_sort_ascending else "DESC"
            cursor.execute(f"""
                SELECT date, machine_name, machine_type, machine_no, start_time, end_time, work_hours, fuel_gallons, remark 
                FROM records 
                ORDER BY (substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) {order_clause}, id {order_clause}
            """)
            rows = cursor.fetchall()

            with open(save_path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Date (dd/mm/yyyy)", "Machine Name", "Type", "Machine No.",
                    "Start Time", "End Time", "Work Hours", "Fuel (Gallons)", "Remark"
                ])
                writer.writerows(rows)

            conn.close()
            show_snack(f"Saved: Download/{file_name}")
        except Exception as err:
            show_snack(f"Error saving CSV: {str(err)}", ft.colors.RED_600)

    def export_summary_csv(e):
        try:
            target_dir = get_download_path()
            from_d = from_date_field.value.strip().replace("/", "-") or "all"
            to_d = to_date_field.value.strip().replace("/", "-") or "time"
            file_name = f"summary_{from_d}_to_{to_d}_{datetime.now().strftime('%H%M%S')}.csv"
            save_path = os.path.join(target_dir, file_name)

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            from_d_val = from_date_field.value.strip()
            to_d_val = to_date_field.value.strip()

            query = """
                SELECT machine_name, machine_type, machine_no, MIN(date), MAX(date), SUM(work_hours), SUM(fuel_gallons)
                FROM records
            """
            params = []
            if from_d_val and to_d_val:
                query += " WHERE date >= ? AND date <= ?"
                params.extend([from_d_val, to_d_val])

            order_clause = "ASC" if sum_sort_ascending else "DESC"
            query += f" GROUP BY machine_name, machine_no ORDER BY (substr(MIN(date), 7, 4) || '-' || substr(MIN(date), 4, 2) || '-' || substr(MIN(date), 1, 2)) {order_clause}"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            with open(save_path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Machine Name", "Type", "Machine No.", "Start Date",
                    "End Date", "Total Hours", "Total Fuel (Gallons)"
                ])
                writer.writerows(rows)

            conn.close()
            show_snack(f"Saved: Download/{file_name}")
        except Exception as err:
            show_snack(f"Error saving CSV: {str(err)}", ft.colors.RED_600)

    # ==========================================
    # SCREEN 1: Register Machines
    # ==========================================
    reg_name_field = ft.TextField(label="Machine Name", hint_text="e.g. Grader / Komatsu")
    reg_type_field = ft.TextField(label="Type", hint_text="e.g. Motor Grader / Excavator")
    reg_no_field = ft.TextField(label="Machine No.", hint_text="e.g. GR-01 / 1B-3456")

    registered_machines_list = ft.Column(spacing=8)

    def load_registered_machines():
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, machine_name, machine_type, machine_no FROM machines ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()

        registered_machines_list.controls.clear()
        for m_id, name, m_type, no in rows:
            def delete_machine(e, m_id=m_id):
                conn_del = sqlite3.connect(DB_NAME)
                cursor_del = conn_del.cursor()
                cursor_del.execute("DELETE FROM machines WHERE id=?", (m_id,))
                conn_del.commit()
                conn_del.close()
                load_registered_machines()
                refresh_dashboard()
                show_snack("Machine deleted.", ft.colors.ORANGE_800)

            registered_machines_list.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(f"{name} ({no or 'No N/A'})", weight=ft.FontWeight.BOLD, size=14),
                                    ft.Text(f"Type: {m_type or '-'}", size=12, color=ft.colors.GREY_700),
                                ],
                                expand=True
                            ),
                            ft.IconButton(
                                icon=ft.icons.DELETE_FOREVER,
                                icon_color=ft.colors.RED_400,
                                on_click=delete_machine
                            )
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    padding=10,
                    bgcolor=ft.colors.GREY_100,
                    border_radius=8,
                    border=ft.border.all(1, ft.colors.GREY_300)
                )
            )
        page.update()

    def add_machine(e=None):
        name = reg_name_field.value.strip()
        m_type = reg_type_field.value.strip()
        no = reg_no_field.value.strip()

        if not name:
            show_snack("Please enter machine name.", ft.colors.RED_400)
            reg_name_field.focus()
            return
        if not m_type:
            show_snack("Please enter machine type.", ft.colors.RED_400)
            reg_type_field.focus()
            return
        if not no:
            show_snack("Please enter machine number.", ft.colors.RED_400)
            reg_no_field.focus()
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO machines (machine_name, machine_type, machine_no) VALUES (?, ?, ?)",
                       (name, m_type, no))
        conn.commit()
        conn.close()

        reg_name_field.value = ""
        reg_type_field.value = ""
        reg_no_field.value = ""

        load_registered_machines()
        refresh_dashboard()
        show_snack("New machine registered successfully.")
        reg_name_field.focus()

    reg_name_field.on_submit = lambda e: reg_type_field.focus() if reg_name_field.value.strip() else show_snack("Please enter machine name.", ft.colors.RED_400)
    reg_type_field.on_submit = lambda e: reg_no_field.focus() if reg_type_field.value.strip() else show_snack("Please enter machine type.", ft.colors.RED_400)
    reg_no_field.on_submit = lambda e: add_machine() if reg_no_field.value.strip() else show_snack("Please enter machine number.", ft.colors.RED_400)

    screen_1_setup = ft.Column(
        controls=[
            ft.Text("Register New Machine", size=16, weight=ft.FontWeight.BOLD),
            ft.Column([reg_name_field, reg_type_field, reg_no_field], spacing=12),
            ft.ElevatedButton(
                "Save Machine",
                icon=ft.icons.ADD,
                style=ft.ButtonStyle(color=ft.colors.WHITE, bgcolor=ft.colors.BLUE_700),
                on_click=add_machine,
                width=300
            ),
            ft.Divider(),
            ft.Text("Registered Machines List", size=15, weight=ft.FontWeight.BOLD),
            registered_machines_list
        ],
        spacing=12,
        scroll=ft.ScrollMode.AUTO
    )

    # ==========================================
    # SCREEN 2: Operations Portal (Dashboard)
    # ==========================================
    selected_date_field = ft.TextField(
        label="Date (dd/mm/yyyy)",
        value="",
        hint_text="DD/MM/YYYY",
        dense=True,
        width=180,
        on_blur=lambda e: refresh_dashboard(),
        on_submit=lambda e: refresh_dashboard()
    )

    def on_date_picked(e):
        if date_picker.value:
            selected_date_field.value = date_picker.value.strftime("%d/%m/%Y")
            refresh_dashboard()

    date_picker = ft.DatePicker(on_change=on_date_picked)

    # Page.open() သို့ ပြောင်းလဲထားပါသည်
    btn_pick_date = ft.IconButton(
        icon=ft.icons.CALENDAR_MONTH,
        tooltip="Select Date",
        on_click=lambda _: page.open(date_picker)
    )

    dashboard_container = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO)
    status_summary_container = ft.Container()

    def update_status_summary():
        rec_date = selected_date_field.value.strip()
        if not rec_date:
            status_summary_container.content = ft.Text("Please enter a date", color=ft.colors.GREY_600)
            status_summary_container.padding = 8
            status_summary_container.bgcolor = ft.colors.GREY_100
            page.update()
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("SELECT id, machine_name, machine_no FROM machines ORDER BY id ASC")
        machines = cursor.fetchall()

        cursor.execute("SELECT machine_id, status FROM machine_status WHERE date=?", (rec_date,))
        status_map = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        working_machines = [m for m in machines if status_map.get(m[0], "idle") == "working"]
        idle_machines = [m for m in machines if status_map.get(m[0], "idle") != "working"]

        working_names = ", ".join([f"{m[1]}({m[2] or 'N/A'})" for m in working_machines])
        idle_names = ", ".join([f"{m[1]}({m[2] or 'N/A'})" for m in idle_machines])

        status_summary_container.content = ft.Column([
            ft.Text(f"📊 {rec_date} Machine Operation Status Summary", weight=ft.FontWeight.BOLD, size=14,
                    color=ft.colors.BLUE_900),
            ft.Divider(height=4),
            ft.Text(f"🟢 Working Machines ({len(working_machines)}): {working_names if working_names else 'None'}",
                    color=ft.colors.GREEN_800, weight=ft.FontWeight.W_500),
            ft.Text(f"🔴 Idle Machines ({len(idle_machines)}): {idle_names if idle_names else 'None'}",
                    color=ft.colors.RED_800, weight=ft.FontWeight.W_500),
        ])
        status_summary_container.padding = 12
        status_summary_container.bgcolor = ft.colors.BLUE_50
        status_summary_container.border_radius = 8
        status_summary_container.border = ft.border.all(1, ft.colors.BLUE_300)
        page.update()

    def build_machine_card(m_id, name, m_type, no):
        rec_date = selected_date_field.value.strip()

        current_status = "idle"
        if rec_date:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM machine_status WHERE date=? AND machine_id=?", (rec_date, m_id))
            row = cursor.fetchone()
            conn.close()
            if row:
                current_status = row[0]

        def auto_calculate_hours(e=None):
            s_obj = parse_time_string(start_time_field.value or "")
            e_obj = parse_time_string(end_time_field.value or "")

            if s_obj and e_obj:
                diff = e_obj - s_obj
                total_hours = diff.total_seconds() / 3600.0
                hours_field.value = f"{max(0.0, total_hours):.2f}"

            page.update()

        def set_start_now(e):
            start_time_field.value = datetime.now().strftime("%I:%M %p")
            auto_calculate_hours()

        def set_end_now(e):
            end_time_field.value = datetime.now().strftime("%I:%M %p")
            auto_calculate_hours()

        start_time_field = ft.TextField(
            label="Start Time", hint_text="08:00 AM", expand=True, dense=True,
            disabled=(current_status == "idle"), on_change=auto_calculate_hours
        )
        end_time_field = ft.TextField(
            label="End Time", hint_text="12:00 PM", expand=True, dense=True,
            disabled=(current_status == "idle"), on_change=auto_calculate_hours
        )

        hours_field = ft.TextField(
            label="Work Hours", value="0.00", expand=True, dense=True,
            disabled=(current_status == "idle")
        )
        fuel_field = ft.TextField(
            label="Fuel (Gallons)", hint_text="0.0", expand=True, dense=True,
            disabled=(current_status == "idle")
        )
        remark_field = ft.TextField(
            label="Remark", hint_text="e.g. Morning / Afternoon", dense=True,
            disabled=(current_status == "idle")
        )

        def on_status_change(e):
            r_date = selected_date_field.value.strip()
            if not r_date:
                show_snack("Please enter a date first above", ft.colors.RED_400)
                return

            selected_st = status_radio.value
            conn_st = sqlite3.connect(DB_NAME)
            cursor_st = conn_st.cursor()
            cursor_st.execute("""
                INSERT INTO machine_status (date, machine_id, status)
                VALUES (?, ?, ?)
                ON CONFLICT(date, machine_id) DO UPDATE SET status=excluded.status
            """, (r_date, m_id, selected_st))
            conn_st.commit()
            conn_st.close()

            is_disabled = (selected_st == "idle")
            start_time_field.disabled = is_disabled
            end_time_field.disabled = is_disabled
            hours_field.disabled = is_disabled
            fuel_field.disabled = is_disabled
            remark_field.disabled = is_disabled
            btn_play.disabled = is_disabled
            btn_stop.disabled = is_disabled
            btn_save.disabled = is_disabled

            update_status_summary()

        status_radio = ft.RadioGroup(
            content=ft.Row([
                ft.Radio(value="working", label="🟢 Working"),
                ft.Radio(value="idle", label="🔴 Idle"),
            ]),
            value=current_status,
            on_change=on_status_change
        )

        btn_play = ft.IconButton(
            icon=ft.icons.PLAY_ARROW, icon_color=ft.colors.WHITE, bgcolor=ft.colors.GREEN_700,
            tooltip="Set Start Time", disabled=(current_status == "idle"), on_click=set_start_now
        )
        btn_stop = ft.IconButton(
            icon=ft.icons.STOP, icon_color=ft.colors.WHITE, bgcolor=ft.colors.RED_700,
            tooltip="Set End Time", disabled=(current_status == "idle"), on_click=set_end_now
        )

        def save_machine_daily_record(e):
            r_date = selected_date_field.value.strip()
            if not r_date or not parse_date_string(r_date):
                show_snack("Please enter a valid date (dd/mm/yyyy)", ft.colors.RED_400)
                return

            start_val = start_time_field.value.strip()
            end_val = end_time_field.value.strip()

            hours_val = hours_field.value.strip()
            fuel_val = fuel_field.value.strip()
            remark_val = remark_field.value.strip()

            try:
                hours_num = float(hours_val) if hours_val else 0.0
                fuel_num = float(fuel_val) if fuel_val else 0.0
            except ValueError:
                show_snack("Please enter numbers for hours and fuel amount only", ft.colors.RED_400)
                return

            if hours_num == 0 and fuel_num == 0 and not remark_val and not start_val:
                show_snack(f"Please enter details for {name}", ft.colors.RED_400)
                return

            conn_rec = sqlite3.connect(DB_NAME)
            cursor_rec = conn_rec.cursor()
            cursor_rec.execute("""
                INSERT INTO records (date, machine_id, machine_name, machine_type, machine_no, start_time, end_time, work_hours, fuel_gallons, remark)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (r_date, m_id, name, m_type, no, start_val, end_val, hours_num, fuel_num, remark_val))
            conn_rec.commit()
            conn_rec.close()

            show_snack(f"Record saved for {name} on {r_date}.")

            start_time_field.value = ""
            end_time_field.value = ""
            hours_field.value = "0.00"
            fuel_field.value = ""
            remark_field.value = ""

            page.update()

        btn_save = ft.ElevatedButton(
            "Save", icon=ft.icons.SAVE,
            style=ft.ButtonStyle(color=ft.colors.WHITE, bgcolor=ft.colors.BLUE_700),
            disabled=(current_status == "idle"),
            on_click=save_machine_daily_record
        )

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(f"{name} ({no or 'No N/A'})", size=15, weight=ft.FontWeight.BOLD),
                    ft.Text(f"Type: {m_type or '-'}", size=11, color=ft.colors.GREY_700)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),

                status_radio,
                ft.Divider(height=4),

                ft.Row([start_time_field, btn_play]),
                ft.Row([end_time_field, btn_stop]),
                ft.Row([hours_field, fuel_field], spacing=10),

                ft.Column([
                    remark_field,
                    ft.Row([btn_save], alignment=ft.MainAxisAlignment.END)
                ], spacing=8)
            ], spacing=8),
            padding=12,
            bgcolor=ft.colors.WHITE,
            border_radius=8,
            border=ft.border.all(1, ft.colors.BLUE_200)
        )

    def refresh_dashboard():
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, machine_name, machine_type, machine_no FROM machines ORDER BY id ASC")
        machines = cursor.fetchall()
        conn.close()

        dashboard_container.controls.clear()
        if not machines:
            dashboard_container.controls.append(
                ft.Text("No machines registered yet. Please add them in the 'Register Machine' tab first.",
                        color=ft.colors.GREY_600))
        else:
            dashboard_container.controls.append(
                ft.Row([
                    ft.Text("Date:", weight=ft.FontWeight.BOLD),
                    selected_date_field,
                    btn_pick_date
                ], alignment=ft.MainAxisAlignment.START)
            )
            dashboard_container.controls.append(status_summary_container)
            dashboard_container.controls.append(ft.Divider())

            for m_id, name, m_type, no in machines:
                dashboard_container.controls.append(build_machine_card(m_id, name, m_type, no))

        update_status_summary()

    # ==========================================
    # SCREEN 3: Daily Detailed Records
    # ==========================================
    rec_sort_ascending = False

    def on_records_sort(e):
        nonlocal rec_sort_ascending
        rec_sort_ascending = not rec_sort_ascending
        load_records_data()

    records_table = ft.DataTable(
        sort_column_index=0,
        sort_ascending=rec_sort_ascending,
        columns=[
            ft.DataColumn(ft.Text("Date ⇕"), on_sort=on_records_sort, tooltip="Sort Ascending/Descending"),
            ft.DataColumn(ft.Text("Machine Name")),
            ft.DataColumn(ft.Text("Start Time")),
            ft.DataColumn(ft.Text("End Time")),
            ft.DataColumn(ft.Text("Hours")),
            ft.DataColumn(ft.Text("Fuel (Gal)")),
            ft.DataColumn(ft.Text("Remark")),
            ft.DataColumn(ft.Text("Action")),
        ],
        rows=[]
    )

    def delete_record_entry(rec_id):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM records WHERE id=?", (rec_id,))
        conn.commit()
        conn.close()
        load_records_data()
        show_snack("Record deleted.", ft.colors.ORANGE_800)

    def load_records_data():
        records_table.sort_ascending = rec_sort_ascending
        order_clause = "ASC" if rec_sort_ascending else "DESC"

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute(f"""
            SELECT id, date, machine_name, start_time, end_time, work_hours, fuel_gallons, remark 
            FROM records 
            ORDER BY (substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) {order_clause}, id {order_clause}
        """)
        rows = cursor.fetchall()
        conn.close()

        records_table.rows.clear()
        for row in rows:
            rec_id = row[0]
            records_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(row[1]))),
                        ft.DataCell(ft.Text(str(row[2]))),
                        ft.DataCell(ft.Text(str(row[3] or ""))),
                        ft.DataCell(ft.Text(str(row[4] or ""))),
                        ft.DataCell(ft.Text(f"{row[5]:.2f}")),
                        ft.DataCell(ft.Text(f"{row[6]:.2f}")),
                        ft.DataCell(ft.Text(str(row[7] or ""))),
                        ft.DataCell(
                            ft.IconButton(
                                icon=ft.icons.DELETE,
                                icon_color=ft.colors.RED_500,
                                tooltip="Delete",
                                on_click=lambda e, r_id=rec_id: delete_record_entry(r_id)
                            )
                        ),
                    ]
                )
            )
        page.update()

    screen_3_records = ft.Column(
        controls=[
            ft.Row(
                [
                    ft.Text("Detailed Records", size=15, weight=ft.FontWeight.BOLD),
                    ft.ElevatedButton(
                        "Export CSV",
                        icon=ft.icons.DOWNLOAD,
                        style=ft.ButtonStyle(bgcolor=ft.colors.GREEN_700, color=ft.colors.WHITE),
                        on_click=export_daily_csv
                    )
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ),
            ft.Row([records_table], scroll=ft.ScrollMode.ALWAYS)
        ],
        spacing=10,
        scroll=ft.ScrollMode.AUTO
    )

    # ==========================================
    # SCREEN 4: Machine Summary Records
    # ==========================================
    sum_sort_ascending = True

    from_date_field = ft.TextField(
        label="From (dd/mm/yyyy)",
        value="",
        hint_text="DD/MM/YYYY",
        expand=True,
        dense=True
    )
    to_date_field = ft.TextField(
        label="To (dd/mm/yyyy)",
        value="",
        hint_text="DD/MM/YYYY",
        expand=True,
        dense=True
    )

    def on_from_date_picked(e):
        if from_date_picker.value:
            from_date_field.value = from_date_picker.value.strftime("%d/%m/%Y")
            page.update()

    def on_to_date_picked(e):
        if to_date_picker.value:
            to_date_field.value = to_date_picker.value.strftime("%d/%m/%Y")
            page.update()

    from_date_picker = ft.DatePicker(on_change=on_from_date_picked)
    to_date_picker = ft.DatePicker(on_change=on_to_date_picked)

    def on_summary_sort(e):
        nonlocal sum_sort_ascending
        sum_sort_ascending = not sum_sort_ascending
        load_summary_data()

    summary_table = ft.DataTable(
        sort_column_index=2,
        sort_ascending=sum_sort_ascending,
        columns=[
            ft.DataColumn(ft.Text("Machine Name")),
            ft.DataColumn(ft.Text("Machine No.")),
            ft.DataColumn(ft.Text("Start Date ⇕"), on_sort=on_summary_sort, tooltip="Sort Ascending/Descending"),
            ft.DataColumn(ft.Text("End Date")),
            ft.DataColumn(ft.Text("Total Hours")),
            ft.DataColumn(ft.Text("Total Fuel (Gal)")),
            ft.DataColumn(ft.Text("Action")),
        ],
        rows=[]
    )

    def delete_summary_group(m_name, m_no):
        from_d = from_date_field.value.strip()
        to_d = to_date_field.value.strip()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        query = "DELETE FROM records WHERE machine_name = ? AND (machine_no = ? OR machine_no IS NULL)"
        params = [m_name, m_no]

        if from_d and to_d:
            query += " AND date >= ? AND date <= ?"
            params.extend([from_d, to_d])

        cursor.execute(query, params)
        conn.commit()
        conn.close()
        load_summary_data()
        show_snack(f"Records for {m_name} deleted.", ft.colors.ORANGE_800)

    def load_summary_data(e=None):
        summary_table.sort_ascending = sum_sort_ascending
        order_clause = "ASC" if sum_sort_ascending else "DESC"

        from_d = from_date_field.value.strip()
        to_d = to_date_field.value.strip()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        query = """
            SELECT machine_name, machine_no, MIN(date), MAX(date), SUM(work_hours), SUM(fuel_gallons)
            FROM records
        """
        params = []

        if from_d and to_d:
            query += " WHERE date >= ? AND date <= ?"
            params.extend([from_d, to_d])

        query += f" GROUP BY machine_name, machine_no ORDER BY (substr(MIN(date), 7, 4) || '-' || substr(MIN(date), 4, 2) || '-' || substr(MIN(date), 1, 2)) {order_clause}"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        summary_table.rows.clear()
        for row in rows:
            m_name = str(row[0])
            m_no = str(row[1] or "")
            summary_table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(m_name)),
                        ft.DataCell(ft.Text(m_no)),
                        ft.DataCell(ft.Text(str(row[2] or "-"))),
                        ft.DataCell(ft.Text(str(row[3] or "-"))),
                        ft.DataCell(ft.Text(f"{row[4] or 0.0:.2f}")),
                        ft.DataCell(ft.Text(f"{row[5] or 0.0:.2f}")),
                        ft.DataCell(
                            ft.IconButton(
                                icon=ft.icons.DELETE_FOREVER,
                                icon_color=ft.colors.RED_600,
                                tooltip="Delete",
                                on_click=lambda e, name=m_name, no=m_no: delete_summary_group(name, no)
                            )
                        )
                    ]
                )
            )
        page.update()

    # Page.open() သို့ ပြောင်းလဲထားပါသည်
    screen_4_summary = ft.Column(
        controls=[
            ft.Text("Machine Summary Report", size=15, weight=ft.FontWeight.BOLD),
            ft.Row([
                from_date_field,
                ft.IconButton(icon=ft.icons.CALENDAR_MONTH, on_click=lambda _: page.open(from_date_picker)),
                to_date_field,
                ft.IconButton(icon=ft.icons.CALENDAR_MONTH, on_click=lambda _: page.open(to_date_picker)),
            ], spacing=5),
            ft.Row([
                ft.ElevatedButton("View", icon=ft.icons.SEARCH, on_click=load_summary_data),
                ft.ElevatedButton(
                    "Export CSV",
                    icon=ft.icons.DOWNLOAD_FOR_OFFLINE,
                    style=ft.ButtonStyle(bgcolor=ft.colors.GREEN_700, color=ft.colors.WHITE),
                    on_click=export_summary_csv
                )
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(),
            ft.Row([summary_table], scroll=ft.ScrollMode.ALWAYS)
        ],
        spacing=10,
        scroll=ft.ScrollMode.AUTO
    )

    # ==========================================
    # NAVIGATION LOGIC
    # ==========================================
    main_content_area = ft.Container(content=dashboard_container, expand=True)
    current_tab = 1

    def switch_screen(tab_index):
        nonlocal current_tab
        current_tab = tab_index

        for i, btn in enumerate([btn_tab1, btn_tab2, btn_tab3, btn_tab4]):
            btn.style = ft.ButtonStyle(
                color=ft.colors.WHITE if current_tab == i else ft.colors.BLUE_800,
                bgcolor=ft.colors.BLUE_800 if current_tab == i else ft.colors.BLUE_50,
            )

        if current_tab == 0:
            load_registered_machines()
            main_content_area.content = screen_1_setup
        elif current_tab == 1:
            refresh_dashboard()
            main_content_area.content = dashboard_container
        elif current_tab == 2:
            load_records_data()
            main_content_area.content = screen_3_records
        elif current_tab == 3:
            load_summary_data()
            main_content_area.content = screen_4_summary

        page.update()

    btn_tab1 = ft.ElevatedButton("Register Machine", icon=ft.icons.SETTINGS,
                                 style=ft.ButtonStyle(color=ft.colors.BLUE_800, bgcolor=ft.colors.BLUE_50),
                                 on_click=lambda _: switch_screen(0))
    btn_tab2 = ft.ElevatedButton("Operations", icon=ft.icons.DASHBOARD,
                                 style=ft.ButtonStyle(color=ft.colors.WHITE, bgcolor=ft.colors.BLUE_800),
                                 on_click=lambda _: switch_screen(1))
    btn_tab3 = ft.ElevatedButton("Detailed CSV", icon=ft.icons.LIST_ALT,
                                 style=ft.ButtonStyle(color=ft.colors.BLUE_800, bgcolor=ft.colors.BLUE_50),
                                 on_click=lambda _: switch_screen(2))
    btn_tab4 = ft.ElevatedButton("Summary CSV", icon=ft.icons.SUMMARIZE,
                                 style=ft.ButtonStyle(color=ft.colors.BLUE_800, bgcolor=ft.colors.BLUE_50),
                                 on_click=lambda _: switch_screen(3))

    nav_bar = ft.Row(
        [btn_tab1, btn_tab2, btn_tab3, btn_tab4],
        scroll=ft.ScrollMode.ALWAYS,
        alignment=ft.MainAxisAlignment.START
    )

    page.add(nav_bar, ft.Divider(height=10), main_content_area)

    load_registered_machines()
    refresh_dashboard()


if __name__ == "__main__":
    ft.app(target=main)