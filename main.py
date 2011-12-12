import urllib2, re, subprocess, sys, os, time, urlparse
import web
import browser, captchasolver, xmltramp
from wyrutils import *
from ClientForm import ParseResponse, ControlNotFoundError, AmbiguityError

import socket; socket.setdefaulttimeout(30)

DEBUG = False
WYR_URL = 'https://writerep.house.gov/writerep/welcome.shtml'
SEN_URL = 'http://senate.gov/general/contact_information/senators_cfm.xml'
WYR_MANUAL = {
  'cleaver': 'http://www.house.gov/cleaver/IMA/issue.htm',
  'quigley': 'http://forms.house.gov/quigley/webforms/issue_subscribe.htm',
  'himes': 'http://himes.house.gov/index.cfm?sectionid=141&sectiontree=54,141',
  'issa': 'http://issa.house.gov/index.php?option=com_content&view=article&id=597&Itemid=73',
  'billnelson': 'http://billnelson.senate.gov/contact/email.cfm', # requires post
  'lautenberg': 'http://lautenberg.senate.gov/contact/index1.cfm',
  'bingaman': 'http://bingaman.senate.gov/contact/types/email-issue.cfm', #email avail
  'johanns': 'http://johanns.senate.gov/public/?p=EmailSenatorJohanns',
  'bennelson': 'http://bennelson.senate.gov/email-issues.cfm',
  'boxer': 'http://boxer.senate.gov/en/contact/policycomments.cfm',
  'warner': 'http://warner.senate.gov/public//index.cfm?p=ContactPage',
  'markudall': 'http://markudall.senate.gov/?p=contact_us',
  'murkowski': 'http://murkowski.senate.gov/public/index.cfm?p=EMailLisa',
  'pryor': 'http://pryor.senate.gov/public/index.cfm?p=ContactForm',
  'sanders': 'http://sanders.senate.gov/contact/contact.cfm',
  'kirk': 'http://kirk.senate.gov/?p=comment_on_legislation',
  'lugar': 'http://lugar.senate.gov/contact/contactform.cfm',
  'harkin': 'http://harkin.senate.gov/contact_opinion.cfm',
  'mikulski': 'http://mikulski.senate.gov/contact/shareyouropinion.cfm',
  'scottbrown': 'http://scottbrown.senate.gov/public/index.cfm/contactme',
  'franken': 'http://franken.senate.gov/?p=email_al',
  'klobuchar': 'http://klobuchar.senate.gov/emailamy.cfm?contactForm=emailamy&submit=Go',
  'levin': 'https://levin.senate.gov/contact/email/',
  'demint': 'http://demint.senate.gov/public/index.cfm?p=CommentOnLegislationIssues',
  'mcconnell': 'http://www.mcconnell.senate.gov/public/index.cfm?p=ContactForm',
  'johnson': 'http://johnson.senate.gov/public/index.cfm?p=ContactForm',
  'thune': 'http://thune.senate.gov/public/index.cfm/contact',
  'fortenberry': 'https://forms.house.gov/fortenberry/webforms/issue_subscribe.html',
  'wassermanschultz': 'http://wassermanschultz.house.gov/contact/email-me.shtml',
  #'jackson': 'https://forms.house.gov/jackson/webforms/issue_subscribe.htm'
}

def get_senate_offices():
    out = {}
    d = xmltramp.load('senators_cfm.xml')
    for member in d: 
        out.setdefault(str(member.state), []).append(str(member.email))
    return out

def getdistzipdict(zipdump):
    """returns a dict with district names as keys zipcodes falling in it as values"""
    d = {}
    for line in zipdump.strip().split('\n'):
        zip5, zip4, district = line.split('\t')
        d[district] = (zip5.strip(), zip4.strip())
    return d

dist_zip_dict = getdistzipdict(file('zip_per_dist.tsv').read())

def getzip(dist):
    try:
        if DEBUG: print dist_zip_dict[dist]
        return dist_zip_dict[dist]
    except Exception:
        return '', ''    

def not_signup_or_search(form):
    has_textarea = form.find_control_by_type('textarea')
    if has_textarea:
        return True
    else:    
        action = form.action
        signup = '/findrep' in action
        search = 'search' in action or 'thomas.loc.gov' in action
        return not(search or signup)

def writerep_ima(ima_link, i, env={}):
    """Sends the msg along with the sender details from `i` through the form @ ima_link.
        The web page at `ima_link` typically has a single form, with the sender's details
        and subject and msg (and with a captcha img for few reps/senators).
        If it has a captcha img, the form to fill captcha is taken from env.
    """
    def check_confirm(request):
        if 'Submit.click' in b.page or "$('idFrm').submit()" in b.page:
            f = get_form(b, lambda f: 'formproc' in f.action)
            if f:
                if DEBUG: print 'Submitting ima confirmation form...',
                return b.open(f.click())
        return request

    def fill_inhofe_lgraham(f, i):
        """special function to fill in forms for inhofe and lgraham"""
        f.fill_all(A01=i.prefix, B01=i.fname, C01=i.lname, D01=i.addr1, E01=i.addr2, F01=i.city,
                   G01=i.state, H01=i.zip5, H02=i.phone, H03=i.phone, I01=i.email, J01="Communications")
        
    b = browser.Browser(env.get('cookies', []))
    b.url, b.page = ima_link, env.get('form')

    f = get_form(b, lambda f: f.find_control_by_type('textarea'))
    
    if not f:
        if DEBUG: print "Form not retrieved.  will open ima_link", ima_link
        b.open(ima_link)
        f = get_form(b, lambda f: f.find_control_by_type('textarea'))

    if f:            
        f.fill_name(i.prefix, i.fname, i.lname)
        f.fill_address(i.addr1, i.addr2)
        f.fill_phone(i.phone)
        f.fill(type='textarea', value=i.full_msg)
        captcha_val = None#i.get('captcha_%s' % pol, '')

        #
        # NKF - 8-Dec-11 - added extra values to handle senator pages where form submission was broken
        #
        #f.fill_all(city=i.city, state=i.state.upper(), zipcode=i.zip5, zip4=i.zip4, email=i.email,
        #            issue=['GEN', 'OTH', ""], subject=i.subject, captcha=captcha_val, reply='yes', newsletter='noAction',
        #            MessageType="Express an opinion or share your views with me", aff1='Unsubscribe')
        f.fill_all(city=i.city, state=i.state.upper(), zipcode=i.zip5, zip4=i.zip4, email=i.email,
                    issue=i.subject,
                    subject=i.subject, captcha=captcha_val, reply='yes', newsletter='noAction',
                    MessageType="Express an opinion or share your views with me", aff1='Unsubscribe',
                    Subject=i.subject, messageSubject=i.subject, view=i.subject, respond="yes")

        if ima_link.find("inhofe") >= 0 or ima_link.find("lgraham") >= 0:
             fill_inhofe_lgraham(f, i)
        
        if DEBUG: print 'Submitting first ima form...', f
        return check_confirm(b.open(f.click()))
    else:
        raise StandardError('No IMA form in: %s' % ima_link)

def writerep_zipauth(zipauth_link, i):
    """Sends the msg along with the sender details from `i` through the WYR system.
      This has 2 forms typically.
      Form 1 asks for zipcode and few user details 
      Form 2 asks for the subject and msg to send and other sender's details.
      Form 3 (sometimes) asks for them to confirm.
    """
    def zipauth_step1(f):
        f.fill_name(i.prefix, i.fname, i.lname)
        f.fill_address(i.addr1, i.addr2)
        f.fill_phone(i.phone)
        f.fill_all(email=i.email, zipcode=i.zip5, zip4=i.zip4, city=i.city)
        if 'lamborn.house.gov' in zipauth_link:
            f.f.action = urlparse.urljoin(zipauth_link, '/Contact/ContactForm.htm') #@@ they do it in ajax
        if DEBUG: print 'Submitting first zip form...',
        return f.click()

    def countforms():
        ''' Count forms in browser.  Used for debugging. '''
        formcount = 0
        for f in b.get_forms():
            if DEBUG: print "form: ", f
            formcount += 1
        return formcount
    
    def zipauth_step2(request):
        request.add_header('Cookie', 'District=%s' % i.zip5)  #@@ done in ajax :(
        response = b.open(request)

        if DEBUG: print "\n count: %d"% countforms()
        f = get_form(b, lambda f: f.find_control_by_type('textarea'))

        if f:
            f.fill_name(i.prefix, i.fname, i.lname)
            f.fill_address(i.addr1, i.addr2)
            f.fill_phone(i.phone)
            f.fill(type='textarea', value=i.full_msg)
            f.fill_all(city=i.city, zipcode=i.zip5, zip4=i.zip4, state=i.state.upper(),
                    email=i.email, issue=['GEN', 'OTH'], subject=i.subject, reply='yes',
                    newsletter='noAction', aff1='Unsubscribe',
                    MessageType="Express an opinion or share your views with me")
            if DEBUG: print 'Submitting second zip form...',
            return b.open(f.click())
        else:
            print >> sys.stderr, 'no form with text area'
            if b.has_text('zip code is split between more'): raise ZipShared
            if b.has_text('Access to the requested form is denied'): raise ZipIncorrect
            if b.has_text('you are outside'): raise ZipIncorrect
            raise StandardError('no form with text area', b.get_text())
    
    def zipauth_step3(request):
        if 'Submit.click' in b.page:
            f = get_form(b, lambda f: 'formproc' in f.action)
            if f:
                if DEBUG: print 'Submitting zip confirmation form...',
                return b.open(f.click())
        return request
            
    b = browser.Browser()
    b.open(zipauth_link)
    form = get_form(b, lambda f: f.has(name='zip'))
    if form:
        return zipauth_step3(zipauth_step2(zipauth_step1(form)))
    else:
        raise StandardError('No zipauth form in: %s' % zipauth_link)

def writerep_wyr(b, form, i):
    """Sends the msg along with the sender details from `i` through the WYR system.
    The WYR system has 3 forms typically (and a captcha form for few reps in between 1st and 2nd forms).
    Form 1 asks for state and zipcode
    Form 2 asks for sender's details such as prefix, name, city, address, email, phone etc
    Form 3 asks for the msg to send.
    """
    def wyr_step1(form):
        if form and form.fill_name(i.prefix, i.fname, i.lname):
            form.fill_address(i.addr1, i.addr2)
            form.fill_all(city=i.city, phone=i.phone, email=i.email)
            request = form.click()
            if DEBUG: print 'Submitting first wyr form...',
            return request
            
    def wyr_step2(request):
        if DEBUG: print request
        b.open(request)
        form = get_form(b, lambda f: f.find_control_by_type('textarea'))
        if form and form.fill(i.full_msg, type='textarea'):
            if DEBUG: print 'Submitting textarea wyr form...',
            return b.open(form.click())
    
    return wyr_step2(wyr_step1(form))
    

r_refresh = re.compile('[Uu][Rr][Ll]=([^"]+)')
writerep_cache = {}


direct_contact_pages= {'UT-03' : 'https://chaffetz.house.gov/contact/email-me.shtml',
                       'CA-03' : 'https://forms.house.gov/matsui/webforms/issue_subscribe.htm',
                       'AR-02' : 'https://timgriffinforms.house.gov/Forms/WriteYourRep/',
                       'AZ-02' : 'http://franks.house.gov/contacts/new'}

def writerep(i):
    """Looks up the right contact page and handles any simple challenges."""
    
    def get_challenge():
        labels = b.find_nodes('label', lambda x: x.get('for') == 'HIP_response')
        if labels: return labels[0].string
    
    b = browser.Browser()

    def step2(request):
        b.open(request)
        newurl = False
        form = get_form(b, not_signup_or_search)
        if not form:
            if b.has_text("is shared by more than one"): raise ZipShared
            elif b.has_text("not correct for the selected State"): raise ZipIncorrect
            elif b.has_text("was not found in our database."): raise ZipNotFound
            elif b.has_text("Use your web browser's <b>BACK</b> capability "): raise WyrError
            else:
                if 'http-equiv="refresh"' in b.page:
                    if DEBUG: print b.page
                    newurl = r_refresh.findall(b.page)[0]
                    if DEBUG: print "Step2 newurl:", newurl
                else:
                    raise NoForm
        else:
            challenge = get_challenge()
            if challenge:
                try:
                    solution = captchasolver.solve(challenge)
                except Exception, detail:
                    print >> sys.stderr, 'Exception in CaptchaSolve', detail
                    print >> sys.stderr, 'Could not solve:"%s"' % challenge,
                else:        
                    form.f['HIP_response'] = str(solution)
                    return step2(form.click())
        return form, newurl
    
            
    zipkey = (i.zip5, i.zip4)
    if zipkey in writerep_cache:
        form = None
        newurl = writerep_cache[zipkey]
        print 'cachehit', len(writerep_cache),
    else:
        b.open(WYR_URL)
        form = get_form(b, not_signup_or_search)
        # state names are in form: "PRPuerto Rico"
        state_options = form.find_control_by_name('state').items
        state_l = [s.name for s in state_options if s.name[:2] == i.state]
        form.fill_all(state=state_l[0], zipcode=i.zip5, zip4=i.zip4)
        form, newurl = step2(form.click())
        if DEBUG: print 'step1 done\n',
        if not form and newurl:
            writerep_cache[zipkey] = newurl
    
    if form:
        return writerep_wyr(b, form, i)
    elif newurl:
        print "newurl : ", newurl

        # this replace was causing a problem with TX-02
        #newurl = newurl.replace(' ', '')
        newurl = newurl.replace(' ', '%20')

        # These 3 lines were causing a problem with Sheila Jackson and Jesse Jackson.
        # For house, would be better to look up by district than name.
        for rep in WYR_MANUAL:
            if rep in newurl:
                newurl = WYR_MANUAL[rep]
                
        b.open(newurl)
        print "newurl: ", newurl
        if DEBUG:
            for form in b.get_forms(): print "step2 form:", form
        if get_form(b, lambda f: f.find_control_by_type('textarea')):
            return writerep_ima(newurl, i)
        elif get_form(b, has_zipauth):
            return writerep_zipauth(newurl, i)
        elif i.dist in direct_contact_pages.keys():
            if DEBUG: print "WYR form did not work.  Trying contact page ", direct_contact_pages[i.dist]
            try:
                return writerep_ima(direct_contact_pages[i.dist], i)
            except:
                try:
                    return writerep_zipauth(direct_contact_pages[i.dist], i)
                except:
                    raise StandardError('unable to use form in direct contact page %s ' % direct_contact_pages[i.dist])
        else:
            print "Can't fill form?"
            if DEBUG:
                for f in b.get_forms():
                    print "Form: ", f
            if DEBUG: print newurl
            raise StandardError('no valid form')

#def contact_dist():
def prepare_i(dist):
    '''
    get the fields for the email form.
    the only thing that changes is the state
    '''
    i = web.storage()
    i.dist=dist
    i.state = dist[:2]
    if len(dist) == 2:
        i.zip5, i.zip4 = getzip(dist + '-00')
        if not i.zip5:
            i.zip5, i.zip4 = getzip(dist + '-01')
    else:
        i.zip5, i.zip4 = getzip(dist)
    
    i.prefix = 'Mr.'
    i.fname = 'James'
    i.lname = 'Smith'
    i.addr1 = '12 Main St'
    i.addr2 = ''
    i.city = 'Franklin'
    i.phone = '571-336-2637'
    # Aaron's
#   i.email = 'demandprogressoutreach@gmail.com'
    # Naomi's
    i.email = 'demandprogressoutreach@yahoo.com'
    i.subject = 'Please oppose the Protect IP Act'
        
    i.full_msg = 'I urge you to reject S. 968, the PROTECT IP Act. (My understanding is that the House is currently developing companion legislation.) I am deeply concerned by the danger the bill poses to Internet security, free speech online, and innovation.  The PROTECT IP Act is dangerous and short-sighted, and I urge you to join Senator Wyden, Rep. Zoe Lofgren, and other members of Congress in opposing it.'
    
    return i


h_working = set(['NE-03', 'MO-08', 'OH-12', 'OH-13', 'OH-16', 'OH-17', 'OH-18', 'MO-01', 'MO-02', 'GA-07', 'MO-04', 'MO-05', 'MO-06', 'MO-07', 'IL-09', 'IL-08', 'MT-00', 'IL-04', 'CT-05', 'IL-06', 'IL-01', 'CT-02', 'IL-03', 'NC-13', 'NY-11', 'IA-01', 'FL-25', 'NH-01', 'KY-05', 'KY-06', 'GU-00', 'GA-05', 'NM-02', 'OH-10', 'IA-05', 'IL-19', 'IL-16', 'IL-17', 'IL-15', 'IL-12', 'IL-13', 'IL-10', 'CA-45', 'NY-03', 'NY-05', 'NY-04', 'NY-07', 'RI-02', 'NY-09', 'PA-10', 'ND-00', 'TN-09', 'CA-25', 'FL-11', 'FL-10', 'FL-13', 'FL-12', 'NC-12', 'FL-16', 'WY-00', 'TN-08', 'CA-46', 'MS-01', 'NY-12', 'NY-13', 'NY-10', 'CA-32', 'NY-16', 'CA-34', 'NY-14', 'HI-02', 'CA-38', 'HI-01', 'CA-41', 'FL-08', 'FL-09', 'CA-42', 'PR-00', 'FL-02', 'FL-03', 'FL-07', 'FL-04', 'FL-05', 'WV-01', 'MI-11', 'WV-03', 'WV-02', 'CA-01', 'NJ-03', 'GA-06', 'TX-30', 'PA-08', 'PA-03', 'PA-02', 'PA-01', 'TX-32', 'PA-05', 'MI-14', 'CA-23', 'KS-04', 'CA-26', 'KS-03', 'NY-29', 'KS-01', 'CA-28', 'CA-07', 'NY-21', 'AL-02', 'CT-03', 'NC-11', 'ID-01', 'PA-11', 'PA-12', 'PA-13', 'MS-04', 'PA-19', 'MS-03', 'VA-01', 'VA-05', 'MN-06', 'MN-04', 'VA-09', 'GA-13', 'GA-12', 'GA-11', 'WI-07', 'OR-01', 'CA-19', 'CA-18', 'NJ-08', 'NJ-09', 'CA-15', 'WI-08', 'CA-12', 'DE-00', 'NV-01', 'NV-03', 'WA-04', 'WA-01', 'WA-03', 'CA-17', 'CO-07', 'CO-04', 'CA-27', 'MA-06', 'NC-06', 'TX-26', 'TX-27', 'TX-24', 'TX-25', 'TX-15', 'CA-13', 'TX-29', 'RI-01', 'GA-08', 'GA-04', 'MI-10', 'MI-13', 'MI-12', 'MI-15', 'GA-01', 'GA-02', 'GA-03', 'VT-00', 'ME-02', 'AR-03', 'AR-01', 'AR-04', 'LA-05', 'LA-04', 'LA-03', 'IN-01', 'CT-01', 'AL-05', 'IN-06', 'AL-07', 'TX-10', 'TX-17', 'IN-02', 'AL-03', 'TX-14', 'UT-02', 'CA-20', 'IN-08', 'MA-10', 'MI-08', 'TN-05', 'AZ-06', 'CA-33', 'MI-02', 'NJ-13', 'MI-01', 'MI-06', 'IN-04', 'MI-04', 'MI-05', 'MD-01', 'TX-13', 'MD-02', 'CA-24', 'MD-07', 'MD-06', 'MD-08', 'CA-51', 'NY-28', 'IN-05', 'FL-22', 'OH-06', 'OH-05', 'AL-06', 'OH-01', 'SC-06', 'IA-02', 'SC-03', 'OH-08', 'TX-09', 'CO-03', 'TX-04', 'TN-03', 'NC-09', 'TX-07', 'TX-03', 'MA-02', 'MA-03', 'TN-04', 'MA-04', 'MA-05', 'MA-08', 'MA-09', 'NC-04', 'CA-39', 'CA-40', 'PA-06', 'FL-23', 'TN-06', 'MI-03', 'NY-15', 'MN-07', 'WI-06', 'IL-02', 'FL-01', 'IA-04', 'OH-15', 'FL-20', 'VA-06', 'VA-02', 'NY-22', 'NY-23', 'AK-00', 'NJ-06', 'TX-21', 'LA-01', 'CA-11', 'OH-04', 'OH-03', 'ID-02', 'TX-01', 'FL-17', 'NY-06', 'TN-01', 'WI-01'])

h_badaddr = set(['IN-07', 'WI-04', 'MO-03', 'CA-53', 'FL-06', 'IL-07', 'KY-04', 'CO-02', 'IL-05', 'MA-01', 'CO-06', 'NJ-12', 'OR-03', 'AZ-04', 'NY-08', 'NY-20', 'NM-03', 'SC-01', 'CA-31', 'TX-28', 'OK-01', 'OK-04', 'WA-09', 'FL-15', 'FL-24', 'TX-16', 'TX-11', 'GA-0'])
h_working.update(h_badaddr)

# MessageType="Express an opinion or share your views with me"
# aff1="Unsubscribe"

def housetest():
    correction = set(['VA-03', 'NE-01', 'DC-00', 'WA-07', 'SD-00', 'OH-02', 'OH-14'])
    err = set(['NE-02', 'FL-24', 'MO-09', 'AZ-03', 'FL-21', 'NY-02', 'CT-04', 'NC-10', 'AZ-07', 'NH-02', 'KY-01', 'KY-02', 'KY-03', 'CA-36', 'NY-01', 'NM-01', 'CA-10', 'IL-18', 'OH-11', 'IL-14', 'OR-04', 'IL-11', 'CA-44', 'OK-03', 'CA-47', 'CA-43', 'CA-48', 'CA-49', 'FL-19', 'NY-06', 'FL-15', 'FL-14', 'OK-02', 'CA-30', 'CA-35', 'NY-17', 'CA-37', 'NY-18', 'NY-19', 'WI-03', 'PA-09', 'VA-07', 'PA-07', 'WI-05', 'PA-04', 'CA-22', 'CA-21', 'KS-02', 'NJ-11', 'NJ-10', 'NY-27', 'NY-26', 'NY-25', 'NY-24', 'PA-14', 'PA-15', 'PA-16', 'PA-17', 'ID-02', 'OK-05', 'PA-18', 'MS-02', 'MN-03', 'MN-02', 'MN-01', 'TX-31', 'VA-04', 'MN-05', 'VA-08', 'MN-08', 'OR-05', 'NJ-01', 'NJ-02', 'GA-10', 'NJ-04', 'NJ-05', 'OR-02', 'CA-16', 'CA-14', 'CA-11', 'WI-01', 'WA-08', 'WI-02', 'NV-02', 'NC-02', 'WA-05', 'WA-06', 'NJ-07', 'WA-02', 'CO-01', 'CO-05', 'TX-08', 'VA-10', 'VA-11', 'TX-22', 'TX-23', 'TX-20', 'CA-08', 'CA-09', 'GA-09', 'TX-05', 'CA-02', 'CA-03', 'CA-04', 'CA-05', 'CA-06', 'ME-01', 'AR-02', 'LA-07', 'LA-02', 'LA-01', 'WA-09', 'AL-04', 'TX-11', 'IN-03', 'TX-16', 'UT-01', 'UT-03', 'TX-18', 'IN-09', 'TN-07', 'AZ-01', 'MI-09', 'TN-02', 'AZ-05', 'TN-01', 'AZ-08', 'IA-03', 'AS-00', 'MD-03', 'MD-05', 'MD-04', 'TX-12', 'CA-52', 'CA-50', 'OH-07', 'OH-04', 'OH-03', 'AL-01', 'SC-04', 'SC-05', 'SC-02', 'OH-09', 'NC-03', 'AZ-02', 'NC-01', 'CA-29', 'NC-07', 'NC-05', 'MI-07', 'TX-06', 'NC-08', 'TX-01', 'TX-02', 'MA-07', 'TX-19', 'FL-18'])


    # 38 judiciary members
    judiciary=set(['TX-21', 'WI-05', 'NC-06', 'CA-24', 'VA-06', 'CA-03', 'OH-01',  'IN-06', 'VA-04', 'IA-05', 'AZ-02', 'TX-01', 'OH-04', 'TX-02', 'UT-03', 'AR-02', 'PA-10', 'SC-04', 'FL-12', 'FL-24', 'AZ-03', 'NV-02', 'MI-14', 'CA-28', 'NY-08', 'VA-03', 'NC-12', 'CA-16', 'TX-18', 'CA-35', 'TN-09', 'GA-04', 'PR-00', 'IL-05', 'CA-32', 'FL-19', 'CA-39'])

    # judiciary members with captchas
    judCaptcha=set(['CA-49', 'MI-14' ])

    n = set()
    n.update(correction); 
    #n.update(err);


    # Speed up test.
    # To check the return pages using pattern matching
    # rather than by eye, set this flag to false
    checkByEye=True
    
    fh = file('results.log', 'a')
    for dist in dist_zip_dict:
        #if dist in h_working or dist in n: continue
        #if dist != 'NC-06': continue
        if dist not in judiciary: continue
        print dist,
        try:
            q = writerep(prepare_i(dist))
            file('%s.html' % dist, 'w').write(q)
            if checkByEye:
                subprocess.Popen(['open', '%s.html' % dist])
                print
                result = raw_input('%s? ' % dist)
            else:
                if 'thank' in q.lower() or 'your message has been submitted' in q.lower() or 'your message has been submitted' in q.lower() : 
                    result='thanked'
                elif 'the street number in the input address was not valid' in q.lower():
                    result='bad-street-address'
                else:
                    result='err'
            print result + '.add(%s)' % repr(dist)
            fh.write('%s.add(%s)\n' % (result, repr(dist)))
        except Exception:
            import traceback; traceback.print_exc()
            print 'err.add(%s)' % repr(dist)
            fh.write('%s.add(%s)\n' % ('err', repr(dist)))
        fh.flush()

def contact_dist(i):
    print i.dist, 
    try:
        #if i.dist not in [x.replace('00', '01') for x in h_working]:
        #    raise StandardError('not working: skipped %s' % i.dist)
        q = writerep(i)
    except Exception, e:
        file('failures.log', 'a').write('%s %s %s\n' % (i.id, i.dist, e))
        print >>sys.stderr, 'fail:', i.dist, e
    print

working = ['coons', 'kohl', 'akaka', 'inouye', 'shaheen', 'menendez', 'cantwell', 'carper', 'manchin', 'rockefeller', 'barrasso', 'ayotte', 'tomudall', 'hutchison', 'landrieu', 'vitter', 'burr', 'conrad', 'johanns', 'bennelson', 'gillibrand', 'schumer', 'casey', 'toomey', 'boxer', 'heller', 'reid', 'bennet', 'markudall', 'sessions', 'boozman', 'leahy', 'sanders', 'kirk', 'isakson', 'coats', 'lugar', 'grassley', 'harkin', 'kyl', 'mccain', 'blumenthal', 'lieberman', 'collins', 'cardin', 'mikulski', 'kerry', 'brown', 'portman', 'mccaskill', 'franken', 'klobuchar', 'levin', 'stabenow', 'reed', 'whitehouse', 'baucus', 'tester', 'cochran', 'wicker', 'paul', 'merkley', 'wyden', 'murray', 'ronjohnson', 'rubio', 'enzi', 'bingaman', 'cornyn', 'hagan', 'hoeven', 'alexander', 'corker', 'warner', 'begich', 'murkowski', 'pryor', 'durbin', 'chambliss', 'coburn', 'snowe', 'scottbrown', 'hatch', 'lee', 'blunt', 'demint', 'mcconnell', 'johnson', 'thune']

def contact_state(i):
    sendb = get_senate_offices()
    for member in sendb.get(i.state, []):
        sen = web.lstrips(web.lstrips(web.lstrips(member, 'http://'), 'https://'), 'www.').split('.')[0]
        if sen in WYR_MANUAL: member = WYR_MANUAL[sen]
        
        print sen,
        try:
            #if sen not in working:
            #    raise StandardError('not working: skipped %s' % sen)
            q = writerep_ima(member, i)
        except Exception, e:
            file('failures.log', 'a').write('%s %s %s\n' % (i.id, member, e))
            print >>sys.stderr, 'fail:', sen, e
    print


def senatetest2(member2email):
    sendb = get_senate_offices()
    for state in sendb:
        for member in sendb[state]:
            sen = web.lstrips(web.lstrips(web.lstrips(member, 'http://'), 'https://'), 'www.').split('.')[0]
            if sen in WYR_MANUAL: member = WYR_MANUAL[sen]
            if sen != member2email : continue
            print repr(sen)
            q = writerep_ima(member, prepare_i(state))
            
            file('sen/%s.html' % sen, 'w').write('<base href="%s"/>' % member + q)

            success=False
            if "thank" in q.lower() or "your message has been submitted" in q.lower() or "your message has been submitted" in q.lower() : 
                #if you're getting thanked, you're probably successful
                success=True
            
            subprocess.Popen(['open', 'sen/%s.html' % sen])
            subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE).stdin.write(', ' + repr(sen))

            if (success):
                print "Successfully wrote to %s" % member2email
            else:
                print "Failed to write to %s" % member2email
            import sys
            sys.exit(1)


def brokensenators():
    '''
    this list was compiled by Aaron.
    For these senators, there were various problems with their
    email submission pages
    '''

    # fixed 1 of the 3
    # lieberman redirects to a page with all these broken links
    # brown never gets to the "Thank you" page
    # hagan - fixed.  needed RESPOND=yes in the form
    unsure = ['lieberman', 'brown', 'hagan']

    #fixed these two
    # inhofe - had to write a special function since the ids in the form fields were weird.
    # same exact function also worked for lgraham
    funnynames = ['inhofe', 'lgraham']

    # fixed these two
    #lautenberg - required field, view
    # webb - homePhone and workPhone fields (not required, but the Form class fill_phone class
    #        was assuming the number should be split into area code and phone number,
    #        so had to fix this).
    e500 = ['lautenberg', 'webb']

    # has a two step process for the email form
    # will take more testing
    requirespost = ['billnelson']

    # didn't find this to be broken
    noformdetect = ['feinstein']

    # no idea what to do with the captcha pages
    captcha = ['shelby', 'crapo', 'risch', 'moran', 'roberts']
    
    failure = e500 + requirespost + captcha + funnynames
    return failure
            
def senatetest():
    '''
    Creates a file sen/schumer.html with schumers contact page
    '''
    sendb = get_senate_offices()
    statfile = open("senate-test-out.txt", "w")
    for state in sendb:
        for member in sendb[state]:
            sen = web.lstrips(web.lstrips(web.lstrips(member, 'http://'), 'https://'), 'www.').split('.')[0]
            if sen in WYR_MANUAL: member = WYR_MANUAL[sen]
            #if sen != 'schumer': continue
            #if sen in working + failure: continue
            print repr(sen)
            q = None

            try:
                q = writerep_ima(member, prepare_i(state))
                file('sen/%s.html' % sen, 'w').write('<base href="%s"/>' % member + q)
                #subprocess.Popen(['open', 'sen/%s.html' % sen])
                #subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE).stdin.write(', ' + repr(sen))
                if q.lower().find("thank") >= 0:
                    status = "Thanked"
                else:
                    status = "Failed.  reason unknown."
            except Exception as e:
                print "Caught exception on senator: %s " % member
                status="failed.  exception occurred %s" % e
            statfile.write("Member: %s, Status: %s\n" % (member, status))
            statfile.flush()
    statfile.close()

from subjects import SUBJECT_DB

def convert_i(r):
    i = web.storage()
    i.id = r.parent_id
    i.state = r.state
    i.zip5, i.zip4 = r.zip, r.plus4
    i.dist = r.us_district.replace('_', '-')
    
    i.prefix = r.get('prefix', 'Mr.').encode('utf8')
    i.fname = r.first_name.encode('utf8')
    i.lname = r.last_name.encode('utf8')
    i.addr1 = r.address1.encode('utf8')
    i.addr2 = r.address2.encode('utf8')
    i.city = r.city.encode('utf8')
    i.phone = '571-336-2637'
    i.email = r.email.encode('utf8')
    i.full_msg = r.value.encode('utf8')
    i.subject = SUBJECT_DB.get(r.page_id, 'Please oppose this bill')
    
    
    return i

def send_to(chamber, pnum, maxtodo):
    '''
    chamber is either S or H for senate or house
    pnum is ?
    maxtodo is ?
    '''
    page_id = pnum
    from config import db
    chamberprefix = {'S': '', 'H': 'H_'}[chamber]
    maxid = int(file('%s/%sMAXID' % (pnum, chamberprefix)).read())
    totaldone = int(file('%s/%sTOTAL' % (pnum, chamberprefix)).read())
    q = 1
    while q:
        tries = 3
        while tries:
            try:
                q = db.select("core_action a join core_user u on (u.id = a.user_id) join core_actionfield f on (a.id=f.parent_id and f.name = 'comment') join core_location l on (l.user_id = u.id)", where="page_id=$page_id and a.id > $maxid", order='a.id asc', limit=5000, vars=locals())
                break
            except Exception:
                q = []
                tries -= 1
		db._ctx.clear()
                import traceback; traceback.print_exc()
                time.sleep(60)
    
        print 'todo:', len(q)
        for r in q:
            if totaldone > maxtodo: return
            print totaldone, maxtodo
            try:
                if chamber == 'S': contact_state(convert_i(r))
                elif chamber == 'H': contact_dist(convert_i(r))
            except Exception:
                import traceback; traceback.print_exc()
            totaldone += 1
            maxid = r.parent_id
            file('%s/%sMAXID' % (pnum, chamberprefix), 'w').write(str(maxid))
            file('%s/%sTOTAL' % (pnum, chamberprefix), 'w').write(str(totaldone))

def send_to_senate(pnum, maxtodo): return send_to('S', pnum, maxtodo)
def send_to_house(pnum, maxtodo): return send_to('H', pnum, maxtodo)

def usage():
    ''' print command line usage '''
    print "htest - house test"
    print "stest - senate test"
    print "Unknown usage"

if __name__ == "__main__":
    import sys
    if sys.argv[1] == 'htest':
        housetest()
        sys.exit(0)
    elif sys.argv[1] == 'stest2':
        member = sys.argv[2]
        senatetest2(member)
        sys.exit(0)
    elif sys.argv[1] == 'stest':
        senatetest()

        sys.exit(0)
    
    if sys.argv[2] == 'make':
        num = sys.argv[1]
        os.mkdir(num)
        file('%s/MAXID' % num, 'w').write('0')
        file('%s/TOTAL' % num, 'w').write('0')
        file('%s/H_MAXID' % num, 'w').write('0')
        file('%s/H_TOTAL' % num, 'w').write('0')
        sys.exit(0)
    
    sPNUM = sys.argv[1]
    sMAXTODO = int(sys.argv[3])
    if sys.argv[2] == 'house':
        send_to_house(sPNUM, sMAXTODO)
    elif sys.argv[2] == 'senate':
        send_to_senate(sPNUM, sMAXTODO)
