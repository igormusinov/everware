from selenium.webdriver.common.by import By
import commons

def scenario_short(user):
    driver = commons.login(user)
    user.wait_for_element_present(By.ID, "start")
    driver.find_element_by_id("logout").click()
    user.log("logout clicked")


def scenario_full(user):
    driver = commons.login(user)
    user.wait_for_element_present(By.ID, "start")
    driver.find_element_by_id("start").click()
    commons.fill_repo_info(driver, user, user.repo)
    user.log("spawn clicked")
    user.wait_for_element_present(By.LINK_TEXT, "Control Panel")
    driver.find_element_by_link_text("Control Panel").click()
    user.wait_for_element_present(By.ID, "stop")
    driver.find_element_by_id("stop").click()
    user.log("stop clicked")
    user.wait_for_pattern_in_page(r"Launch\s+a\s+notebook")
    driver.find_element_by_id("logout").click()
    user.log("logout clicked")


def scenario_no_jupyter(user):
    driver = commons.login(user)
    user.wait_for_element_present(By.ID, "start")
    driver.find_element_by_id("start").click()
    commons.fill_repo_info(driver, user, 'docker:busybox')
    user.log("spawn clicked")
    user.wait_for_element_present(By.ID, "resist")
    text = ("Something went wrong during building."
            " Error: Container doesn't have jupyter-singleuser inside")
    assert text in driver.page_source
    user.log("correct, no jupyter in container")
    driver.find_element_by_id("resist").click()
    commons.fill_repo_info(driver, user, user.repo)
    user.log("spawn clicked (second try)")
    user.wait_for_element_present(By.LINK_TEXT, "Control Panel")
    driver.find_element_by_link_text("Control Panel").click()
    user.wait_for_element_present(By.ID, "stop")
    driver.find_element_by_id("stop").click()
    user.log("stop clicked")
    user.wait_for_pattern_in_page(r"Launch\s+a\s+notebook")
    driver.find_element_by_id("logout").click()
    user.log("logout clicked")


def scenario_timeout(user):
    driver = commons.login(user)
    user.wait_for_element_present(By.ID, "start")
    driver.find_element_by_id("start").click()
    commons.fill_repo_info(driver, user, 'https://github.com/everware/test_long_creation')
    user.log("spawn clicked")
    user.wait_for_element_present(By.ID, "resist")
    assert "Building took too long" in driver.page_source or \
            "This image is too heavy to build" in driver.page_source
    user.log('correct, timeout happened')
    driver.find_element_by_id("resist").click()
    user.log("resist clicked")
    commons.fill_repo_info(driver, user, 'https://github.com/everware/test_long_creation')
    user.log("spawn clicked (second try)")
    user.wait_for_element_present(By.ID, "resist")
    assert "This image is too heavy to build" in driver.page_source


def scenario_no_dockerfile(user):
    driver = commons.login(user)
    user.wait_for_element_present(By.ID, "start")
    driver.find_element_by_id("start").click()
    commons.fill_repo_info(driver, user, 'https://github.com/everware/runnable_examples')
    user.log("spawn clicked")
    user.wait_for_element_present(By.ID, "resist")
    text = ("Something went wrong during building."
            " Error: Your repo doesn't include Dockerfile")
    assert text in driver.page_source
    user.log("correct, no dockerfile")

