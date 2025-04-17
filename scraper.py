from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

session_driver = None

def init_driver(email, password):
    global session_driver
    if session_driver:
        return session_driver

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    session_driver = webdriver.Chrome(options=options)

    session_driver.get("https://www.mydailyfeedback.com/index.php/users/login")
    time.sleep(2)

    email_input = session_driver.find_element(By.CSS_SELECTOR, "input[placeholder='Email']")
    email_input.send_keys(email)

    password_input = session_driver.find_element(By.CSS_SELECTOR, "input[placeholder='Password']")
    password_input.send_keys(password)
    password_input.send_keys(Keys.RETURN)

    time.sleep(3)
    return session_driver

def get_client_feedback_by_id(email, password, client_id, date):
    driver = init_driver(email, password)
    feedback_url = f"https://www.mydailyfeedback.com/index.php/feedbacks/tutor_edit/{date}/{client_id}"
    driver.get(feedback_url)
    time.sleep(3)

    try:
        return driver.find_element(By.TAG_NAME, "body").text
    except Exception as e:
        print("Error retrieving client feedback:", e)
        return "[Error] Unable to fetch feedback."

def get_dashboard_sections(email, password):
    driver = init_driver(email, password)
    driver.get("https://www.mydailyfeedback.com/index.php/people/tutor_view")
    time.sleep(3)

    weekend_reports = []
    waiting_for_response = []
    feedback_report = {
        "Missed 5+ Days": [],
        "Missed 4 Days": [],
        "Missed 3 Days": [],
        "Missed 2 Days": [],
        "Missed Yesterday": []
    }

    # Weekend Reports
    try:
        callouts = driver.find_elements(By.CLASS_NAME, "callout")
        for callout in callouts:
            try:
                header = callout.find_element(By.TAG_NAME, "h6").text.strip()
                if "Weekend Reports" in header:
                    table = callout.find_element(By.TAG_NAME, "table")
                    rows = table.find_elements(By.TAG_NAME, "tr")[1:]  # skip header
                    for row in rows:
                        link = row.find_element(By.TAG_NAME, "a")
                        name = link.text
                        href = link.get_attribute("href")
                        date = href.split("/")[-2]
                        client_id = href.split("/")[-1]
                        weekend_reports.append({"name": name, "date": date, "id": client_id})
                    break
            except:
                continue
    except Exception as e:
        print("Weekend Reports section not found:", e)

        # Reports Waiting For A Response
    try:
        callouts = driver.find_elements(By.CLASS_NAME, "callout")
        for callout in callouts:
            try:
                header = callout.find_element(By.TAG_NAME, "h6").text.strip()
                print(f"[Debug] Checking callout header: {header}")
                if "Reports Waiting For A Response" in header:
                    table = callout.find_element(By.TAG_NAME, "table")
                    rows = table.find_elements(By.TAG_NAME, "tr")[1:]  # skip header
                    for row in rows:
                        try:
                            cells = row.find_elements(By.TAG_NAME, "td")
                            if len(cells) < 3:
                                continue
                            link = cells[0].find_element(By.TAG_NAME, "a")
                            name = link.text.strip()
                            href = link.get_attribute("href")
                            date = cells[1].text.strip()
                            submitted_when = cells[2].text.strip()
                            client_id = href.split("/")[-1]
                            date_path = href.split("/")[-2]

                            print(f"[Debug] Found client: {name} | client_id={client_id} | date={date_path} | submitted_when={submitted_when}")

                            waiting_for_response.append({
                                "name": name,
                                "date": date_path,
                                "submitted_when": submitted_when,
                                "id": client_id
                            })
                        except Exception as row_err:
                            print(f"[Warning] Skipping row due to error: {row_err}")
                    break  # stop after this callout
            except Exception as block_err:
                print(f"[Warning] Failed processing callout block: {block_err}")
    except Exception as e:
        print("Reports Waiting For A Response section not found:", e)

    # Feedback Report
    try:
        report_section = driver.find_element(By.XPATH, "//h5[contains(text(),'Feedback Report')]/..")
        for category in feedback_report.keys():
            try:
                ul = report_section.find_element(By.XPATH, f".//strong[contains(text(),'{category}')]/following-sibling::ul[1]")
                items = ul.find_elements(By.TAG_NAME, "li")
                feedback_report[category] = [item.text for item in items]
            except:
                continue
    except Exception as e:
        print("Feedback Report section not found:", e)

    return {
        "weekend_reports": weekend_reports,
        "waiting_for_response": waiting_for_response,
        "feedback_report": feedback_report
    }
