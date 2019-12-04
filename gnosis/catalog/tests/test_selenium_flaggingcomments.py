import unittest
from selenium import webdriver
from selenium.webdriver.common.by import By
from catalog.models import Comment, Paper
from catalog.forms import FlaggedCommentForm
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from django.contrib.auth.models import User

class ChromeTestCase(unittest.TestCase):
    """test with Chrome webdriver"""

    def createUsers(self):
        """create two users, user2's info will be used for logging in"""

        self.username = 'user1'
        self.userpassword = '12345'
        self.useremail = 'somthing@gnosis.stellargraph.io'

        self.user2name = 'user2'
        self.user2password = 'abcde'
        self.user2email = 'somethingelse@gnosis.stellargraph.io'

        self.user = User.objects.create_user(username=self.username, password=self.userpassword,
                                             email=self.useremail)


        self.user2 = User.objects.create_user(username=self.user2name,
                                                   password=self.user2password,
                                                   email=self.user2email)

    def createPaper(self):
        """create a paper, created by user1"""

        self.paper = Paper.objects.create(
            title="Best paper in the world",
            abstract="The nature of gravity.",
            download_link="https://google.com",
            created_by=self.user,
        )

    def createComment(self):
        """create a comment, with is_flagged as False"""

        self.comment = Comment.objects.create(
            text="testing comment",
            created_by=self.user,
            is_flagged=False,
            is_hidden=False,
            paper=self.paper
        )

    def createAssets(self):
        """create all necessary assets"""

        self.createUsers()
        self.createPaper()
        self.createComment()

    def fillFlagForm(self, flag_form):
        """fill in the flag form"""

        # select the first violation
        input_0 = flag_form.find_element_by_id('id_violation_0')
        input_0.click()
        # find description text area, empty the field and insert text
        description_elements = flag_form.find_element_by_id('id_description')
        description_elements.clear()
        description_elements.send_keys('violation description')

    def setupBrowser(self):
        """set up testing browser"""

        self.browser = webdriver.Chrome()

    def setUp(self):
        """Log in and set up global variables"""

        # create temporary assets for testing
        self.createAssets()
        self.setupBrowser()

        # login as user by first typing the login info on the login form, then submit
        self.browser.get('http://127.0.0.1:8000/accounts/login/?next=/catalog/paper/' + str(self.paper.id) + '/')
        username = self.browser.find_element_by_id('id_login')
        username.clear()
        username.send_keys(self.user2name)

        pwd = self.browser.find_element_by_id('id_password')
        pwd.clear()
        pwd.send_keys(self.user2password)
        self.browser.find_element_by_tag_name('form').submit()
        # wait for Ajax response
        wait = WebDriverWait(self.browser, 10)
        element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'ul.list-group')))
        self.comment_container = self.browser.find_element_by_css_selector('ul.list-group')
        # there should be only one comment in this fictional paper
        self.first_comment = self.comment_container.find_element_by_css_selector('li.list-group-item')

    def tearDown(self):
        """remove temporary assets from DB"""

        self.user.delete()
        self.user2.delete()
        self.paper.delete()
        self.comment.delete()
        self.browser.quit()

    def test_flaggingcomments(self):
        """test all actions for flagging a comment"""

        first_comment = self.first_comment
        browser = self.browser
        flag_form_container = browser.find_element_by_id('flag_form_container')

        # test the flag is an outlined flag for unflagged comment
        text = first_comment.find_element_by_class_name('material-icons').text
        self.assertEqual(text, 'outlined_flag')

        # test pop up flag form is shown when flag icon is clicked
        flag_clickable = first_comment.find_element_by_class_name('open_flag_dialog')
        flag_clickable.click()
        a1 = flag_form_container.get_attribute('hidden')
        self.assertEqual(a1, None)

        # test flag form has the right fields
        flag_form = browser.find_element_by_id('flag_form')
        violations = flag_form.find_element_by_id('id_violation')
        labels = violations.find_elements_by_tag_name('label')
        true_violations = FlaggedCommentForm().fields['violation'].choices
        true_labels = [v[0] for v in true_violations]

        # test radio buttons have the right labels.
        for i in range(len(labels)):
            self.assertEqual(true_labels[i], labels[i].text)

        # test the form has one description field
        description = flag_form.find_elements_by_tag_name('textarea')
        self.assertEqual(len(description), 1)
        desc_id = description[0].get_attribute('id')
        self.assertEqual(desc_id, 'id_description')

        # find first select option and select
        self.fillFlagForm(flag_form)

        # test the cancel button works
        flag_form.find_element_by_tag_name('button').click()
        self.assertEqual(flag_form_container.get_attribute('hidden'), 'true')

        # test the choice and description are cleared after clicking cancel button
        choice = flag_form.find_element_by_id('id_violation_0')
        self.assertFalse(choice.is_selected())
        text = flag_form.find_element_by_id('id_description')
        self.assertFalse(text.get_attribute('value'))

        # reopen the form
        flag_clickable.click()
        self.fillFlagForm(flag_form)

        flag_form.submit()
        # wait for Ajax response
        wait = WebDriverWait(browser, 10)
        element = wait.until(EC.visibility_of_element_located((By.ID, 'flag_response')))

        # after submit, test flag form is hidden
        a1 = browser.find_element_by_id('flag_form_container').get_attribute('hidden')
        self.assertEqual(a1, 'true')
        # test flag_response is unhidden after successful submit
        flag_response = browser.find_element_by_id('flag_response')
        self.assertEqual(flag_response.get_attribute('hidden'), None)

        # test the flagged comment has a filled flag icon attached
        arr = first_comment.find_elements_by_class_name("flagged")
        self.assertEqual(len(arr), 1)
        arr = first_comment.find_elements_by_class_name("material-icons")
        self.assertEqual(arr[0].text, "flag")

class FirfoxTestCase(ChromeTestCase):
    """test with Firefox webdriver"""

    def setupBrowser(self):
        """set the webdriver to Firefox"""
        self.browser = webdriver.Firefox()


if __name__ == '__main__':
    # 2 (verbose): you get the help string of every test and the result
    unittest.main(verbosity=2)
