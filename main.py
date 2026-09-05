import csv
from datetime import datetime
import os
import sqlite3
import flet as ft

# Dynamic Flet module reference to support multiple Flet versions without IDE inspection warnings
colors = getattr(ft, "colors", getattr(ft, "Colors", None))
icons = getattr(ft, "icons", getattr(ft, "Icons", None))
border = getattr(ft, "border", getattr(ft, "Border", None))


# Border Helper Function
def get_border_all(width, color):
    if hasattr(ft, "border") and hasattr(ft.border, "all"):
        return ft.border.all(width, color)
    elif hasattr(ft, "Border") and hasattr(ft.Border, "all"):
        return ft.Border.all(width, color)
    elif border and hasattr(border, "all"):
        return border.all(width, color)
    return None


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
            machine_no TEXT,
            operator TEXT
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
            operator TEXT,
            start_time TEXT,
            end_time TEXT,
            work_hours REAL NOT NULL,
            fuel_gallons REAL DEFAULT 0,
            remark TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_today_machines (
            machine_id INTEGER PRIMARY KEY,
            added_date TEXT NOT NULL
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

    # Database Schema Migration
    cursor.execute("PRAGMA table_info(machines)")
    m_columns = [col[1] for col in cursor.fetchall()]
    if "operator" not in m_columns:
        cursor.execute("ALTER TABLE machines ADD COLUMN operator TEXT")

    cursor.execute("PRAGMA table_info(records)")
    r_columns = [col[1] for col in cursor.fetchall()]
    if "operator" not in r_columns:
        cursor.execute("ALTER TABLE records ADD COLUMN operator TEXT")

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


def get_download_path():
    """Android / Storage Path Detection"""
    android_download_path = "/storage/emulated/0/Download"
    if os.path.exists(android_download_path):
        return android_download_path

    user_download_path = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.exists(user_download_path):
        return user_download_path

    return os.getcwd()


def format_capital_title(text_val: str) -> str:
    """စာလုံးများကို ရှေ့ဆုံးစာလုံးအကြီး နောက်စာလုံးအသေး (Title Case) သို့ ပြောင်းလဲခြင်း"""
    if not text_val:
        return ""
    return text_val.strip().title()


def clean_outdated_daily_operations():
    """ဒီနေ့ မနက် 0:00 မှ ည 12:00 ပြည့်ပြီး နောက်နေ့ရောက်ပါက Active Machines များအား Auto Clean လုပ်ခြင်း"""
    today_str = datetime.now().strftime("%d/%m/%Y")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM active_today_machines WHERE added_date != ?", (today_str,))
    conn.commit()
    conn.close()


def main(page: ft.Page):
    page.title = "Machine Hours and Fuel Record Management"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 10

    # Font Setup
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    font_path = os.path.join(assets_dir, "Pyidaungsu-2.5_Regular.ttf")
    if os.path.exists(font_path):
        page.fonts = {"Pyidaungsu": "assets/Pyidaungsu-2.5_Regular.ttf"}
        page.theme = ft.Theme(font_family="Pyidaungsu")

    init_db()
    clean_outdated_daily_operations()

    def show_snack(msg: str, color=colors.GREEN_700 if colors else None):
        snack = ft.SnackBar(ft.Text(msg, color=colors.WHITE if colors else None), bgcolor=color)
        page.overlay.append(snack)
        snack.open = True
        page.update()

    # Filter State variable across screens
    search_filter_text = ft.Ref[ft.TextField]()

    # ==========================================
    # EXPORT CSV LOGIC (Modified to include Titles/Headers)
    # ==========================================
    def export_single_machine_csv(target_date, m_id, m_name, m_no):
        try:
            target_dir = get_download_path()

            clean_date = target_date.replace("/", "-")
            clean_name = m_name.replace(" ", "_")
            clean_no = (m_no or "no").replace(" ", "_")
            file_name = f"{clean_name}_{clean_no}_{clean_date}_{datetime.now().strftime('%H%M%S')}.csv"
            save_path = os.path.join(target_dir, file_name)

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            query = """
                SELECT 
                    r.id, 
                    r.machine_id, 
                    r.machine_name, 
                    r.machine_type, 
                    r.machine_no, 
                    r.operator,
                    r.start_time, 
                    r.end_time, 
                    r.work_hours, 
                    r.fuel_gallons, 
                    COALESCE(ms.status, 'working') AS status,
                    r.remark 
                FROM records r
                LEFT JOIN machine_status ms 
                    ON r.date = ms.date AND r.machine_id = ms.machine_id
                WHERE r.date = ? AND r.machine_id = ?
                ORDER BY r.id ASC
            """

            cursor.execute(query, (target_date, m_id))
            rows = cursor.fetchall()

            if not rows:
                show_snack(f"No records found for {m_name} on {target_date}.", colors.ORANGE_800 if colors else None)
                conn.close()
                return

            with open(save_path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)

                writer.writerow([f"Machine Operation Report: {m_name} ({m_no or 'N/A'})"])
                writer.writerow([f"Date: {target_date}"])
                writer.writerow([])

                writer.writerow([
                    "Sr No.", "Record ID", "Machine Name", "Machine Type", "Machine No.",
                    "Operator", "Operation Status", "Start Time", "End Time", "Work Hours",
                    "Fuel Consumed (Gallons)", "Fuel Consumption Rate (Gal/Hr)", "Remark"
                ])

                total_hours = 0.0
                total_fuel = 0.0

                for idx, row in enumerate(rows, 1):
                    rec_id, m_id_val, name_val, type_val, no_val, op_name, s_time, e_time, w_hrs, f_gal, status, remark = row
                    rate = round(f_gal / w_hrs, 2) if w_hrs > 0 else 0.0
                    total_hours += w_hrs
                    total_fuel += f_gal

                    writer.writerow([
                        idx, rec_id, name_val, type_val or "-", no_val or "-", op_name or "-",
                        status.capitalize(), s_time or "-", e_time or "-", f"{w_hrs:.2f}",
                        f"{f_gal:.2f}", f"{rate:.2f}", remark or "-"
                    ])

                writer.writerow([])
                writer.writerow([
                    "TOTAL", "", "", "", "", "", "", "", "",
                    f"{total_hours:.2f}", f"{total_fuel:.2f}", "", ""
                ])

            conn.close()
            show_snack(f"Saved: Download/{file_name}")
        except Exception as err:
            show_snack(f"Error saving CSV: {str(err)}", colors.RED_600 if colors else None)

    # ==========================================
    # SCREEN 1: Register Machines
    # ==========================================
    reg_name_field = ft.TextField(label="Machine Name", hint_text="e.g. Grader/Roller/Exacavator")
    reg_type_field = ft.TextField(label="Type", hint_text="e.g. Komatsu/Hyundi/Watanabe")
    reg_no_field = ft.TextField(label="Machine No.", hint_text="e.g. 1B-123")
    reg_operator_field = ft.TextField(label="Operator Name")

    registered_machines_list = ft.Column(spacing=8)

    def add_to_today_operations(m_id):
        clean_outdated_daily_operations()
        today_str = datetime.now().strftime("%d/%m/%Y")
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO active_today_machines (machine_id, added_date)
            VALUES (?, ?)
            ON CONFLICT(machine_id) DO UPDATE SET added_date=excluded.added_date
        """, (m_id, today_str))
        conn.commit()
        conn.close()
        switch_screen(1)

    def load_registered_machines():
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, machine_name, machine_type, machine_no, operator FROM machines ORDER BY id DESC")
        rows = cursor.fetchall()
        conn.close()

        registered_machines_list.controls.clear()
        for m_id, name, m_type, no, op_name in rows:
            def delete_machine(_, target_m_id=m_id):
                conn_del = sqlite3.connect(DB_NAME)
                cursor_del = conn_del.cursor()
                cursor_del.execute("DELETE FROM machines WHERE id=?", (target_m_id,))
                cursor_del.execute("DELETE FROM active_today_machines WHERE machine_id=?", (target_m_id,))
                conn_del.commit()
                conn_del.close()
                load_registered_machines()
                refresh_dashboard()
                show_snack("Machine deleted.", colors.ORANGE_800 if colors else None)

            display_str = f"{name}({no or 'N/A'}),type:{m_type or 'N/A'},operator:{op_name or 'N/A'}"

            registered_machines_list.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(display_str, weight=ft.FontWeight.BOLD, size=13, color=colors.BLUE_900 if colors else None),
                                ],
                                expand=True
                            ),
                            ft.IconButton(
                                icon=getattr(icons, "DELETE_FOREVER", "delete_forever") if icons else "delete_forever",
                                icon_color=colors.RED_400 if colors else None,
                                on_click=delete_machine
                            )
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    padding=12,
                    bgcolor=colors.GREY_100 if colors else None,
                    border_radius=8,
                    border=get_border_all(1, colors.GREY_300 if colors else None),
                    ink=True,
                    on_click=lambda _, target_m_id=m_id: add_to_today_operations(target_m_id)
                )
            )
        page.update()

    def add_machine(_=None):
        name = format_capital_title(reg_name_field.value)
        m_type = format_capital_title(reg_type_field.value)
        no = format_capital_title(reg_no_field.value)
        op_name = format_capital_title(reg_operator_field.value)

        if not name:
            show_snack("Please enter machine name.", colors.RED_400 if colors else None)
            reg_name_field.focus()
            return
        if not m_type:
            show_snack("Please enter machine type.", colors.RED_400 if colors else None)
            reg_type_field.focus()
            return
        if not no:
            show_snack("Please enter machine number.", colors.RED_400 if colors else None)
            reg_no_field.focus()
            return
        if not op_name:
            show_snack("Please enter operator name.", colors.RED_400 if colors else None)
            reg_operator_field.focus()
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO machines (machine_name, machine_type, machine_no, operator) VALUES (?, ?, ?, ?)",
                       (name, m_type, no, op_name))
        conn.commit()
        conn.close()

        reg_name_field.value = ""
        reg_type_field.value = ""
        reg_no_field.value = ""
        reg_operator_field.value = ""

        load_registered_machines()
        refresh_dashboard()
        show_snack("New machine registered successfully.")
        reg_name_field.focus()

    reg_name_field.on_submit = lambda _: reg_type_field.focus()
    reg_type_field.on_submit = lambda _: reg_no_field.focus()
    reg_no_field.on_submit = lambda _: reg_operator_field.focus()
    reg_operator_field.on_submit = lambda _: add_machine()

    screen_1_setup = ft.Column(
        controls=[
            ft.Text("Register New Machine", size=16, weight=ft.FontWeight.BOLD),
            ft.Column([reg_name_field, reg_type_field, reg_no_field, reg_operator_field], spacing=12),
            ft.ElevatedButton(
                "Save Machine",
                icon=getattr(icons, "ADD", "add") if icons else "add",
                style=ft.ButtonStyle(color=colors.WHITE if colors else None, bgcolor=colors.BLUE_700 if colors else None),
                on_click=add_machine,
                width=300
            ),
            ft.Divider(),
            ft.Text("Registered Machines List (Click to Add to Today's Operation)", size=14, weight=ft.FontWeight.BOLD,
                    color=colors.BLUE_800 if colors else None),
            registered_machines_list
        ],
        spacing=10,
        scroll=ft.ScrollMode.AUTO,
        expand=True
    )

    # ==========================================
    # SCREEN 2: Operations Portal (Dashboard & Today Summary)
    # ==========================================
    dashboard_container = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
    status_summary_container = ft.Container()

    def update_status_summary():
        clean_outdated_daily_operations()
        rec_date = datetime.now().strftime("%d/%m/%Y")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT m.id, m.machine_name, m.machine_no, m.operator 
            FROM machines m
            INNER JOIN active_today_machines a ON m.id = a.machine_id
            WHERE a.added_date = ?
            ORDER BY m.id ASC
        """, (rec_date,))
        machines = cursor.fetchall()
        conn.close()

        working_names = ", ".join([f"{m[1]}({m[2] or 'N/A'})" for m in machines])

        status_summary_container.content = ft.Column([
            ft.Text(f"📊 Today's ({rec_date}) Machine Operation Summary", weight=ft.FontWeight.BOLD, size=14,
                    color=colors.BLUE_900 if colors else None),
            ft.Divider(height=4),
            ft.Text(f"🟢 Active Machines ({len(machines)}): {working_names if working_names else 'None'}",
                    color=colors.GREEN_800 if colors else None, weight=ft.FontWeight.W_500),
        ], spacing=6)

        status_summary_container.padding = 12
        status_summary_container.bgcolor = colors.BLUE_50 if colors else None
        status_summary_container.border_radius = 8
        status_summary_container.border = get_border_all(1, colors.BLUE_300 if colors else None)
        page.update()

    def build_machine_card(m_id, name, m_type, no, op_name):
        def set_start_now(_):
            start_time_field.value = datetime.now().strftime("%I:%M %p")
            page.update()

        def set_end_now(_):
            end_time_field.value = datetime.now().strftime("%I:%M %p")
            page.update()

        start_time_field = ft.TextField(
            label="Start Time", hint_text="08:00 AM", expand=True, dense=True
        )
        end_time_field = ft.TextField(
            label="End Time", hint_text="12:00 PM", expand=True, dense=True
        )

        fuel_field = ft.TextField(
            label="Fuel (Gallons)", hint_text="0.0", expand=True, dense=True
        )
        remark_field = ft.TextField(
            label="Remark", hint_text="e.g. Morning / Afternoon", dense=True
        )

        btn_play = ft.IconButton(
            icon=getattr(icons, "PLAY_ARROW", "play_arrow") if icons else "play_arrow",
            icon_color=colors.WHITE if colors else None,
            bgcolor=colors.GREEN_700 if colors else None,
            tooltip="Set Start Time", on_click=set_start_now
        )
        btn_stop = ft.IconButton(
            icon=getattr(icons, "STOP", "stop") if icons else "stop",
            icon_color=colors.WHITE if colors else None,
            bgcolor=colors.RED_700 if colors else None,
            tooltip="Set End Time", on_click=set_end_now
        )

        def save_machine_daily_record(_):
            r_date = datetime.now().strftime("%d/%m/%Y")
            start_val = start_time_field.value.strip()
            end_val = end_time_field.value.strip()

            s_obj = parse_time_string(start_val)
            e_obj = parse_time_string(end_val)
            hours_num = 0.0

            if s_obj and e_obj:
                diff = e_obj - s_obj
                hours_num = max(0.0, diff.total_seconds() / 3600.0)

            fuel_val = fuel_field.value.strip()
            remark_val = remark_field.value.strip()

            try:
                fuel_num = float(fuel_val) if fuel_val else 0.0
            except ValueError:
                show_snack("Please enter numbers for fuel amount only", colors.RED_400 if colors else None)
                return

            if hours_num == 0 and fuel_num == 0 and not remark_val and not start_val:
                show_snack(f"Please enter details for {name}", colors.RED_400 if colors else None)
                return

            conn_rec = sqlite3.connect(DB_NAME)
            cursor_rec = conn_rec.cursor()
            cursor_rec.execute("""
                INSERT INTO records (date, machine_id, machine_name, machine_type, machine_no, operator, start_time, end_time, work_hours, fuel_gallons, remark)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (r_date, m_id, name, m_type, no, op_name, start_val, end_val, hours_num, fuel_num, remark_val))
            conn_rec.commit()
            conn_rec.close()

            show_snack(f"Record saved for {name} ({hours_num:.2f} hrs).")

            start_time_field.value = ""
            end_time_field.value = ""
            fuel_field.value = ""
            remark_field.value = ""

            refresh_dashboard()

        btn_save = ft.ElevatedButton(
            "Add Record",
            icon=getattr(icons, "ADD", "add") if icons else "add",
            style=ft.ButtonStyle(color=colors.WHITE if colors else None, bgcolor=colors.BLUE_700 if colors else None),
            on_click=save_machine_daily_record
        )

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text(f"{name} ({no or 'N/A'})", size=15, weight=ft.FontWeight.BOLD),
                    ft.Text(f"Operator: {op_name or '-'}", size=12, color=colors.BLUE_800 if colors else None, weight=ft.FontWeight.W_500)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Text(f"Type: {m_type or '-'}", size=11, color=colors.GREY_700 if colors else None),

                ft.Divider(height=4),

                ft.Row([start_time_field, btn_play]),
                ft.Row([end_time_field, btn_stop]),
                ft.Row([fuel_field], spacing=10),

                ft.Column([
                    remark_field,
                    ft.Row([btn_save], alignment=ft.MainAxisAlignment.END)
                ], spacing=8)
            ], spacing=8),
            padding=12,
            bgcolor=colors.WHITE if colors else None,
            border_radius=8,
            border=get_border_all(1, colors.BLUE_200 if colors else None)
        )

    def refresh_dashboard():
        clean_outdated_daily_operations()
        rec_date = datetime.now().strftime("%d/%m/%Y")

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.id, m.machine_name, m.machine_type, m.machine_no, m.operator 
            FROM machines m
            INNER JOIN active_today_machines a ON m.id = a.machine_id
            WHERE a.added_date = ?
            ORDER BY m.id ASC
        """, (rec_date,))
        machines = cursor.fetchall()
        conn.close()

        dashboard_container.controls.clear()
        if not machines:
            dashboard_container.controls.append(
                ft.Container(
                    content=ft.Text(
                        "No active machines selected for today. Please click machines in 'Register Machine' tab to add them to today's operations.",
                        color=colors.GREY_700 if colors else None, weight=ft.FontWeight.BOLD),
                    padding=15,
                    bgcolor=colors.AMBER_50 if colors else None,
                    border_radius=8,
                    border=get_border_all(1, colors.AMBER_300 if colors else None)
                )
            )
        else:
            dashboard_container.controls.append(
                ft.Row([
                    ft.Text(f"Today's Date: {rec_date}", weight=ft.FontWeight.BOLD, size=15, color=colors.BLUE_900 if colors else None),
                ], alignment=ft.MainAxisAlignment.START)
            )
            dashboard_container.controls.append(status_summary_container)
            dashboard_container.controls.append(ft.Divider())

            for m_id, name, m_type, no, op_name in machines:
                dashboard_container.controls.append(build_machine_card(m_id, name, m_type, no, op_name))

        update_status_summary()

    # ==========================================
    # SCREEN 3: Detailed Records
    # ==========================================
    date_sort_descending = True
    screen_3_records_container = ft.Column(spacing=10)
    detail_search_field = ft.TextField(
        ref=search_filter_text,
        label="Filter by Machine / Operator",
        hint_text="Type machine name or operator...",
        prefix_icon=getattr(icons, "SEARCH", "search") if icons else "search",
        dense=True,
        on_change=lambda _: load_records_data()
    )

    def toggle_date_sort(_):
        nonlocal date_sort_descending
        date_sort_descending = not date_sort_descending
        btn_date_sort.text = "Sort: Newest First" if date_sort_descending else "Sort: Oldest First"
        btn_date_sort.icon = getattr(icons, "ARROW_DOWNWARD" if date_sort_descending else "ARROW_UPWARD", "arrow_downward") if icons else ("arrow_downward" if date_sort_descending else "arrow_upward")
        load_records_data()

    # Fixed: Changed keyword argument text= to positional argument to support all Flet versions
    btn_date_sort = ft.ElevatedButton(
        "Sort: Newest First",
        icon=getattr(icons, "ARROW_DOWNWARD", "arrow_downward") if icons else "arrow_downward",
        style=ft.ButtonStyle(bgcolor=colors.BLUE_100 if colors else None, color=colors.BLUE_900 if colors else None),
        on_click=toggle_date_sort
    )

    def delete_record_entry(rec_id):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM records WHERE id=?", (rec_id,))
        conn.commit()
        conn.close()
        load_records_data()
        show_snack("Record deleted.", colors.ORANGE_800 if colors else None)

    def load_records_data(_=None, filter_keyword=None):
        clean_outdated_daily_operations()
        today_str = datetime.now().strftime("%d/%m/%Y")

        if filter_keyword is not None:
            detail_search_field.value = filter_keyword

        search_kw = (detail_search_field.value or "").strip().lower()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        sort_order = "DESC" if date_sort_descending else "ASC"
        cursor.execute(f"""
            SELECT DISTINCT date 
            FROM records 
            ORDER BY (substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) {sort_order}
        """)
        dates_rows = cursor.fetchall()

        screen_3_records_container.controls.clear()

        if not dates_rows:
            screen_3_records_container.controls.append(
                ft.Container(
                    content=ft.Text("No records found in database.", color=colors.GREY_700 if colors else None, weight=ft.FontWeight.BOLD),
                    padding=15,
                    bgcolor=colors.AMBER_50 if colors else None,
                    border_radius=8,
                    border=get_border_all(1, colors.AMBER_300 if colors else None)
                )
            )
            conn.close()
            page.update()
            return

        for d_row in dates_rows:
            rec_date = d_row[0]

            cursor.execute("""
                SELECT DISTINCT machine_id, machine_name, machine_type, machine_no, operator
                FROM records
                WHERE date = ?
                ORDER BY machine_id ASC
            """, (rec_date,))
            active_machines = cursor.fetchall()

            machine_tiles = []

            for m_id, m_name, m_type, m_no, op_name in active_machines:
                if search_kw:
                    match_str = f"{m_name} {m_type} {m_no} {op_name}".lower()
                    if search_kw not in match_str:
                        continue

                cursor.execute("""
                    SELECT id, start_time, end_time, work_hours, fuel_gallons, remark
                    FROM records
                    WHERE date = ? AND machine_id = ?
                    ORDER BY id ASC
                """, (rec_date, m_id))
                rec_rows = cursor.fetchall()

                table_rows = []
                m_total_hours = 0.0
                m_total_fuel = 0.0

                for row in rec_rows:
                    rec_id, s_time, e_time, w_hrs, f_gal, r_mark = row
                    m_total_hours += w_hrs
                    m_total_fuel += f_gal

                    table_rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(str(s_time or "-"))),
                                ft.DataCell(ft.Text(str(e_time or "-"))),
                                ft.DataCell(ft.Text(f"{w_hrs:.2f}")),
                                ft.DataCell(ft.Text(f"{f_gal:.2f}")),
                                ft.DataCell(ft.Text(str(r_mark or "-"))),
                                ft.DataCell(
                                    ft.IconButton(
                                        icon=getattr(icons, "DELETE", "delete") if icons else "delete",
                                        icon_color=colors.RED_500 if colors else None,
                                        tooltip="Delete",
                                        on_click=lambda _, target_id=rec_id: delete_record_entry(target_id)
                                    )
                                ),
                            ]
                        )
                    )

                machine_table = ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Text("Start")),
                        ft.DataColumn(ft.Text("End")),
                        ft.DataColumn(ft.Text("Hours")),
                        ft.DataColumn(ft.Text("Fuel (Gal)")),
                        ft.DataColumn(ft.Text("Remark")),
                        ft.DataColumn(ft.Text("Action")),
                    ],
                    rows=table_rows
                )

                summary_banner = ft.Container(
                    content=ft.Text(
                        f"Daily Total: {m_total_hours:.2f} Hrs | {m_total_fuel:.2f} Gal",
                        weight=ft.FontWeight.BOLD,
                        size=13,
                        color=colors.BLUE_900 if colors else None
                    ),
                    padding=8,
                    bgcolor=colors.BLUE_100 if colors else None,
                    border_radius=6,
                    margin=ft.margin.only(bottom=8)
                )

                m_expansion_tile = ft.ExpansionTile(
                    title=ft.Row([
                        ft.Column([
                            ft.Row([
                                ft.Text(f"{m_name} ({m_no or 'N/A'})", size=15, weight=ft.FontWeight.BOLD,
                                        color=colors.BLUE_900 if colors else None),
                                ft.Text(f"|  Operator: {op_name or '-'}", size=13, weight=ft.FontWeight.W_500,
                                        color=colors.BLUE_800 if colors else None),
                            ], spacing=6),
                            ft.Text(f"Type: {m_type or '-'}", size=12, color=colors.GREY_700 if colors else None),
                        ]),
                        ft.ElevatedButton(
                            "CSV Save",
                            icon=getattr(icons, "DOWNLOAD", "download") if icons else "download",
                            style=ft.ButtonStyle(bgcolor=colors.GREEN_700 if colors else None, color=colors.WHITE if colors else None),
                            on_click=lambda _, rdate=rec_date, mid=m_id, mname=m_name,
                                            mno=m_no: export_single_machine_csv(rdate, mid, mname, mno)
                        )
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    initially_expanded=bool(search_kw),
                    controls=[
                        ft.Container(
                            content=ft.Column([
                                summary_banner,
                                ft.Row([machine_table], scroll=ft.ScrollMode.ALWAYS) if table_rows else ft.Text(
                                    "No entries recorded.", color=colors.GREY_600 if colors else None, italic=True)
                            ], spacing=6),
                            padding=10
                        )
                    ]
                )

                machine_tiles.append(
                    ft.Container(
                        content=m_expansion_tile,
                        bgcolor=colors.WHITE if colors else None,
                        border_radius=6,
                        border=get_border_all(1, colors.BLUE_100 if colors else None),
                        margin=ft.margin.only(bottom=6)
                    )
                )

            if machine_tiles:
                date_expansion_tile = ft.ExpansionTile(
                    title=ft.Text(
                        f"📅 Date: {rec_date} ({'Today' if rec_date == today_str else 'Past Record'})",
                        size=16,
                        weight=ft.FontWeight.BOLD,
                        color=colors.BLUE_900 if colors else None
                    ),
                    initially_expanded=bool(search_kw),
                    controls=[
                        ft.Container(
                            content=ft.Column(machine_tiles, spacing=6),
                            padding=10
                        )
                    ]
                )

                screen_3_records_container.controls.append(
                    ft.Container(
                        content=date_expansion_tile,
                        bgcolor=colors.BLUE_50 if colors else None,
                        border_radius=8,
                        border=get_border_all(1, colors.BLUE_300 if colors else None)
                    )
                )

        conn.close()
        page.update()

    screen_3_records = ft.Column(
        controls=[
            ft.Row([
                ft.Text("Machine Detail CSV Records", size=15, weight=ft.FontWeight.BOLD),
                btn_date_sort
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            detail_search_field,
            screen_3_records_container
        ],
        spacing=8,
        scroll=ft.ScrollMode.AUTO,
        alignment=ft.MainAxisAlignment.START,
        expand=True
    )

    # ==========================================
    # SCREEN 4: Summary Screen (Date Range & Machine Filter)
    # ==========================================
    def clear_field_on_focus(field):
        field.value = ""
        page.update()

    from_date_field = ft.TextField(
        label="From Date (DD/MM/YYYY)",
        hint_text="e.g. 01/09/2026",
        dense=True,
        expand=True,
        on_focus=lambda _: clear_field_on_focus(from_date_field)
    )
    to_date_field = ft.TextField(
        label="To Date (DD/MM/YYYY)",
        hint_text="e.g. 30/09/2026",
        dense=True,
        expand=True,
        on_focus=lambda _: clear_field_on_focus(to_date_field)
    )
    machine_dropdown = ft.Dropdown(
        label="Select Machine",
        options=[ft.dropdown.Option(key="ALL", text="All Machines")],
        value="ALL",
        dense=True,
        expand=True
    )

    summary_result_container = ft.Column(spacing=10)
    current_summary_cache = []

    def load_machine_options():
        """Populate Machine Dropdown from registered machines"""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, machine_name, machine_no FROM machines ORDER BY machine_name ASC")
        rows = cursor.fetchall()
        conn.close()

        opts = [ft.dropdown.Option(key="ALL", text="All Machines")]
        for m_id, name, no in rows:
            opts.append(ft.dropdown.Option(key=str(m_id), text=f"{name} ({no or 'N/A'})"))
        machine_dropdown.options = opts
        page.update()

    def parse_ddmmyyyy(d_str):
        try:
            return datetime.strptime(d_str.strip(), "%d/%m/%Y")
        except ValueError:
            return None

    # ==========================================
    # EXPORT SUMMARY CSV LOGIC
    # ==========================================
    def export_summary_csv(_):
        if not current_summary_cache:
            show_snack("No summary data to export.", colors.ORANGE_800 if colors else None)
            return

        try:
            target_dir = get_download_path()
            f_date = from_date_field.value.strip().replace("/", "-") if from_date_field.value else "All"
            t_date = to_date_field.value.strip().replace("/", "-") if to_date_field.value else "All"
            file_name = f"Summary_{f_date}_to_{t_date}_{datetime.now().strftime('%H%M%S')}.csv"
            save_path = os.path.join(target_dir, file_name)

            with open(save_path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)

                writer.writerow(["Machine Operations Summary Report"])
                writer.writerow(
                    [f"Date Range: From {from_date_field.value or 'Beginning'} To {to_date_field.value or 'Present'}"])
                writer.writerow([])

                writer.writerow([
                    "Sr No.", "Machine Name", "Machine Type", "Machine No.",
                    "Operator", "Total Hours", "Total Fuel (Gallons)", "Avg Rate (Gal/Hr)"
                ])

                tot_hrs = 0.0
                tot_fuel = 0.0

                for idx, row in enumerate(current_summary_cache, 1):
                    m_name, m_type, m_no, op_name, hours, fuel = row
                    rate = round(fuel / hours, 2) if hours > 0 else 0.0
                    tot_hrs += hours
                    tot_fuel += fuel

                    writer.writerow([
                        idx, m_name, m_type or "-", m_no or "-", op_name or "-",
                        f"{hours:.2f}", f"{fuel:.2f}", f"{rate:.2f}"
                    ])

                writer.writerow([])
                writer.writerow([
                    "GRAND TOTAL", "", "", "", "",
                    f"{tot_hrs:.2f}", f"{tot_fuel:.2f}", ""
                ])

            show_snack(f"Summary Exported: Download/{file_name}")
        except Exception as err:
            show_snack(f"Error exporting CSV: {str(err)}", colors.RED_600 if colors else None)

    def calculate_summary(_=None):
        nonlocal current_summary_cache
        from_str = from_date_field.value.strip() if from_date_field.value else ""
        to_str = to_date_field.value.strip() if to_date_field.value else ""

        from_dt = parse_ddmmyyyy(from_str) if from_str else None
        to_dt = parse_ddmmyyyy(to_str) if to_str else None

        if from_str and not from_dt:
            show_snack("Invalid From Date format. Use DD/MM/YYYY", colors.RED_400 if colors else None)
            return
        if to_str and not to_dt:
            show_snack("Invalid To Date format. Use DD/MM/YYYY", colors.RED_400 if colors else None)
            return

        selected_m_id = machine_dropdown.value

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        query = """
            SELECT date, machine_id, machine_name, machine_type, machine_no, operator, work_hours, fuel_gallons
            FROM records
        """
        cursor.execute(query)
        all_records = cursor.fetchall()
        conn.close()

        grouped_data = {}

        for r_date, m_id, name, m_type, m_no, op_name, w_hrs, f_gal in all_records:
            r_dt = parse_ddmmyyyy(r_date)
            if not r_dt:
                continue

            if from_dt and r_dt < from_dt:
                continue
            if to_dt and r_dt > to_dt:
                continue

            if selected_m_id != "ALL" and str(m_id) != selected_m_id:
                continue

            if m_id not in grouped_data:
                grouped_data[m_id] = {
                    "name": name,
                    "type": m_type or "-",
                    "no": m_no or "-",
                    "operator": op_name or "-",
                    "hours": 0.0,
                    "fuel": 0.0
                }

            grouped_data[m_id]["hours"] += w_hrs
            grouped_data[m_id]["fuel"] += f_gal

        summary_result_container.controls.clear()
        current_summary_cache = []

        if not grouped_data:
            summary_result_container.controls.append(
                ft.Container(
                    content=ft.Text("No records found for the selected filter.", color=colors.GREY_700 if colors else None,
                                    weight=ft.FontWeight.BOLD),
                    padding=15,
                    bgcolor=colors.AMBER_50 if colors else None,
                    border_radius=8,
                    border=get_border_all(1, colors.AMBER_300 if colors else None)
                )
            )
            page.update()
            return

        table_rows = []
        grand_hours = 0.0
        grand_fuel = 0.0

        for m_id, info in grouped_data.items():
            hrs = info["hours"]
            fuel = info["fuel"]
            rate = round(fuel / hrs, 2) if hrs > 0 else 0.0

            grand_hours += hrs
            grand_fuel += fuel

            current_summary_cache.append((info["name"], info["type"], info["no"], info["operator"], hrs, fuel))

            table_rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(f"{info['name']} ({info['no']})")),
                        ft.DataCell(ft.Text(info["operator"])),
                        ft.DataCell(ft.Text(f"{hrs:.2f}")),
                        ft.DataCell(ft.Text(f"{fuel:.2f}")),
                        ft.DataCell(ft.Text(f"{rate:.2f}")),
                    ]
                )
            )

        summary_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Machine Name (No)")),
                ft.DataColumn(ft.Text("Operator")),
                ft.DataColumn(ft.Text("Total Hours")),
                ft.DataColumn(ft.Text("Total Fuel (Gal)")),
                ft.DataColumn(ft.Text("Avg Rate (Gal/Hr)")),
            ],
            rows=table_rows
        )

        grand_total_card = ft.Container(
            content=ft.Column([
                ft.Text("📊 Overall Range Grand Total", weight=ft.FontWeight.BOLD, size=15, color=colors.BLUE_900 if colors else None),
                ft.Divider(height=4),
                ft.Row([
                    ft.Text(f"Total Work Hours: {grand_hours:.2f} Hrs", weight=ft.FontWeight.BOLD,
                            color=colors.GREEN_800 if colors else None),
                    ft.Text(f"Total Fuel Consumed: {grand_fuel:.2f} Gal", weight=ft.FontWeight.BOLD,
                            color=colors.BLUE_800 if colors else None),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            ], spacing=6),
            padding=12,
            bgcolor=colors.BLUE_50 if colors else None,
            border_radius=8,
            border=get_border_all(1, colors.BLUE_300 if colors else None)
        )

        summary_result_container.controls.extend([
            grand_total_card,
            ft.Row([
                ft.Text("Machine Totals Summary", size=14, weight=ft.FontWeight.BOLD, color=colors.BLUE_900 if colors else None),
                ft.ElevatedButton(
                    "Export Summary CSV",
                    icon=getattr(icons, "DOWNLOAD", "download") if icons else "download",
                    style=ft.ButtonStyle(bgcolor=colors.GREEN_700 if colors else None, color=colors.WHITE if colors else None),
                    on_click=export_summary_csv
                )
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([summary_table], scroll=ft.ScrollMode.ALWAYS)
        ])

        page.update()

    def set_quick_range(days):
        """Quick date range selector helper"""
        now = datetime.now()
        to_date_field.value = now.strftime("%d/%m/%Y")
        if days == "today":
            from_date_field.value = now.strftime("%d/%m/%Y")
        elif days == "month":
            from_date_field.value = datetime(now.year, now.month, 1).strftime("%d/%m/%Y")
        calculate_summary()

    from_date_field.on_submit = lambda _: to_date_field.focus()
    to_date_field.on_submit = lambda _: calculate_summary()
    machine_dropdown.on_change = lambda _: calculate_summary()

    btn_filter = ft.ElevatedButton(
        "Filter Range",
        icon=getattr(icons, "FILTER_ALT", "filter_alt") if icons else "filter_alt",
        style=ft.ButtonStyle(bgcolor=colors.BLUE_700 if colors else None, color=colors.WHITE if colors else None),
        on_click=calculate_summary
    )

    screen_4_summary = ft.Column(
        controls=[
            ft.Text("Machine Operations Summary & Analytics", size=16, weight=ft.FontWeight.BOLD),
            ft.Row([
                ft.OutlinedButton("Today", on_click=lambda _: set_quick_range("today")),
                ft.OutlinedButton("This Month", on_click=lambda _: set_quick_range("month")),
            ], spacing=10),
            ft.Row([from_date_field, to_date_field], spacing=10),
            ft.Row([machine_dropdown, btn_filter], spacing=10),
            ft.Divider(),
            summary_result_container
        ],
        spacing=10,
        scroll=ft.ScrollMode.AUTO,
        expand=True
    )

    # ==========================================
    # NAVIGATION LOGIC & SIDE BAR LAYOUT
    # ==========================================
    screens = [screen_1_setup, dashboard_container, screen_3_records, screen_4_summary]
    current_tab = 0

    main_content_area = ft.Container(
        content=screens[current_tab],
        expand=True,
        padding=10,
        alignment=ft.alignment.top_left
    )

    sidebar_expanded = True

    def toggle_sidebar(_):
        nonlocal sidebar_expanded
        sidebar_expanded = not sidebar_expanded
        sidebar.width = 220 if sidebar_expanded else 70
        update_sidebar_content()
        page.update()

    sidebar_header = ft.Container()
    sidebar_column = ft.Column(spacing=8)

    def update_sidebar_content():
        sidebar_header.content = ft.Row(
            [
                ft.Text("Menu", size=16, weight=ft.FontWeight.BOLD, color=colors.BLUE_900 if colors else None, visible=sidebar_expanded),
                ft.IconButton(
                    icon=getattr(icons, "MENU_OPEN" if sidebar_expanded else "MENU", "menu_open" if sidebar_expanded else "menu") if icons else ("menu_open" if sidebar_expanded else "menu"),
                    icon_color=colors.BLUE_900 if colors else None,
                    tooltip="Collapse/Expand Menu",
                    on_click=toggle_sidebar
                )
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN if sidebar_expanded else ft.MainAxisAlignment.CENTER
        )

        def make_nav_btn(idx, text, icon_name):
            is_selected = (current_tab == idx)
            ic_val = getattr(icons, icon_name, icon_name.lower()) if icons else icon_name.lower()
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ic_val, color=colors.WHITE if is_selected else (colors.BLUE_900 if colors else None), size=20),
                        ft.Text(text, color=colors.WHITE if is_selected else (colors.BLUE_900 if colors else None),
                                weight=ft.FontWeight.W_500, visible=sidebar_expanded)
                    ],
                    spacing=10,
                ),
                bgcolor=(colors.BLUE_800 if is_selected else colors.TRANSPARENT) if colors else None,
                padding=10,
                border_radius=8,
                ink=True,
                on_click=lambda _: switch_screen(idx),
                tooltip=text if not sidebar_expanded else None
            )

        sidebar_column.controls = [
            sidebar_header,
            ft.Divider(),
            make_nav_btn(0, "Register Machine", "SETTINGS"),
            make_nav_btn(1, "Operations", "DASHBOARD"),
            make_nav_btn(2, "Detailed CSV", "LIST_ALT"),
            make_nav_btn(3, "Summary", "ANALYTICS"),
        ]

    sidebar = ft.Container(
        content=sidebar_column,
        width=220,
        bgcolor=colors.BLUE_50 if colors else None,
        padding=10,
        border_radius=8,
        border=get_border_all(1, colors.BLUE_200 if colors else None)
    )

    def switch_screen(tab_index):
        nonlocal current_tab
        if 0 <= tab_index < len(screens):
            current_tab = tab_index

            if current_tab == 0:
                load_registered_machines()
            elif current_tab == 1:
                refresh_dashboard()
            elif current_tab == 2:
                load_records_data()
            elif current_tab == 3:
                load_machine_options()
                calculate_summary()

            update_sidebar_content()
            main_content_area.content = screens[current_tab]
            page.update()

    def handle_pan_update(e: ft.DragUpdateEvent):
        dx = getattr(e, "delta_x", getattr(e, "delta_dx", 0))
        if dx > 20:
            if current_tab > 0:
                switch_screen(current_tab - 1)
        elif dx < -20:
            if current_tab < len(screens) - 1:
                switch_screen(current_tab + 1)

    # Main Layout combining Sidebar and Content Area horizontally
    body_layout = ft.Row(
        [
            sidebar,
            ft.VerticalDivider(width=1),
            ft.GestureDetector(
                content=main_content_area,
                on_pan_update=handle_pan_update,
                expand=True
            )
        ],
        expand=True,
        alignment=ft.MainAxisAlignment.START,
        vertical_alignment=ft.CrossAxisAlignment.START
    )

    page.add(body_layout)

    # Initial App Load
    switch_screen(0)


if __name__ == "__main__":
    ft.app(target=main)
