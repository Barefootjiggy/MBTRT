import os
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

session_driver = None

def init_driver(email, password):
    global session_driver
    if session_driver:
        return session_driver

    # grab Heroku buildpack paths
    chrome_bin   = os.getenv("GOOGLE_CHROME_BIN")
    driver_path  = os.getenv("CHROMEDRIVER_PATH")

    # configure ChromeOptions
    options = Options()
    if chrome_bin:
        options.binary_location = chrome_bin
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # configure Service
    service = Service(executable_path=driver_path)

    # spin up the driver
    session_driver = webdriver.Chrome(service=service, options=options)

    # log in
    session_driver.get("https://www.mydailyfeedback.com/index.php/users/login")
    time.sleep(2)
    session_driver.find_element(By.CSS_SELECTOR, "input[placeholder='Email']").send_keys(email)
    pwd = session_driver.find_element(By.CSS_SELECTOR, "input[placeholder='Password']")
    pwd.send_keys(password)
    pwd.send_keys(Keys.RETURN)
    time.sleep(3)

    return session_driver

def get_client_feedback_by_id(email, password, client_id, date):
    driver = init_driver(email, password)
    feedback_url = f"https://www.mydailyfeedback.com/index.php/feedbacks/tutor_edit/{date}/{client_id}"
    driver.get(feedback_url)
    time.sleep(3)

    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text

        # Extract both ratings
        star_rating = extract_star_rating_visual(driver)
        exercise_rating = extract_exercise_rating_visual(driver)

        # Save full HTML to inspect later
        html = driver.page_source
        # ✅ Save full HTML for inspection/debugging
        with open("raw_feedback.html", "w", encoding="utf-8") as f:
            f.write(html)
        section_images = extract_feedback_images_by_section(html)

        # Replace food rating line
        if star_rating is not None:
            star_word = "star" if star_rating == 1 else "stars"
            body_text = re.sub(
                r"(Rate how well you ate today:\s*)(.*?)(\s*(Cups|Ounces) of water:)",
                rf"\1{'⭐' * star_rating} ({star_rating} {star_word})\3",
                body_text,
                flags=re.DOTALL
            )

        # Replace exercise rating line
        if exercise_rating is not None:
            star_word = "star" if exercise_rating == 1 else "stars"
            body_text = re.sub(
                r"(Rate today's activity\s*\(Only if you had any\):)\s*[\d\s]+",
                f"\\1 {'⭐' * exercise_rating} ({exercise_rating} {star_word})",
                body_text,
                flags=re.DOTALL
            )
        
        body_text = inject_images_to_sections(body_text, section_images)

        # Group images by nearest meal marker if found
        meal_blocks = {}
        for i in range(1, 7):
            pattern = rf"(Meal {i}:.*?)((Meal \d+:)|$)"
            match = re.search(pattern, body_text, flags=re.DOTALL)
            if match:
                meal_blocks[f"Meal {i}"] = match.group(1).strip()

        return body_text

    except Exception as e:
        print("Error retrieving client feedback:", e)
        return "[Error] Unable to fetch feedback."

def extract_feedback_images_by_section(html):
    soup = BeautifulSoup(html, "html.parser")
    section_images = {f"Meal {i}": [] for i in range(1, 7)}
    section_images["MY WORKOUT"] = []

    # Meal-based images
    for a_tag in soup.find_all("a", attrs={"data-fancybox": True}):
        key = a_tag.get("data-fancybox")
        src = a_tag.get("href")
        if not src or not src.startswith("https://ucarecdn.com/"):
            continue

        if key and key.startswith("mealPhotos"):
            meal_num = key.replace("mealPhotos", "").strip()
            meal_key = f"Meal {meal_num}"
            if meal_key in section_images:
                section_images[meal_key].append(src)

        elif key == "gallery":
            section_images["MY WORKOUT"].append(src)

    return section_images

def inject_images_to_sections(body_text, section_images):
    for section, urls in section_images.items():
        if urls:
            img_html = "".join([f'<br><img src="{url}" style="max-width:300px;"><br>' for url in urls])
            if section.startswith("Meal"):
                pattern = rf"({re.escape(section)}:\s*.*?)((?=\s*Meal|\s*$))"
                body_text = re.sub(
                    pattern,
                    rf"\1{img_html}\2",
                    body_text,
                    flags=re.DOTALL
                )
            elif section == "MY WORKOUT":
                pattern = r"(Rate today's activity\s*\(Only if you had any\):.*?\(.*?\))"
                body_text = re.sub(
                    pattern,
                    rf"\1{img_html}",
                    body_text,
                    flags=re.DOTALL
                )
    return body_text

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

def extract_star_rating_visual(driver):
    """
    Extracts the food rating (Part 1).
    """
    try:
        stars = driver.find_elements(
            By.CSS_SELECTOR, "#starRating_Feedback_food_rating .star-rating-on"
        )
        return len(stars)
    except Exception as e:
        print("[Food Rating Extraction Error]:", e)
        return None

def extract_exercise_rating_visual(driver):
    """
    Extracts the exercise rating (Part 2).
    """
    try:
        stars = driver.find_elements(
            By.CSS_SELECTOR, "#starRating_Feedback_exercise_rating .star-rating-on"
        )
        return len(stars)
    except Exception as e:
        print("[Exercise Rating Extraction Error]:", e)
        return None
   
