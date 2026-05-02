import re
import json
from urllib.parse import urlparse
from urllib.parse import unquote
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from urllib.parse import urldefrag
from collections import Counter


unique_pages = set()
longest_page = {'url': '', 'word_count': 0}
subdomains = {}
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before",
    "being", "below", "between", "both", "but", "by", "can't", "cannot",
    "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing",
    "don't", "down", "during", "each", "few", "for", "from", "further", "had",
    "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd",
    "he'll", "he's", "her", "here", "here's", "hers", "herself", "him",
    "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", "i've", "if",
    "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's", "me",
    "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off",
    "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves",
    "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's",
    "should", "shouldn't", "so", "some", "such", "than", "that", "that's",
    "the", "their", "theirs", "them", "themselves", "then", "there", "there's",
    "these", "they", "they'd", "they'll", "they're", "they've", "this",
    "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't",
    "what", "what's", "when", "when's", "where", "where's", "which", "while",
    "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your",
    "yours", "yourself", "yourselves"
}
COUNTS = Counter()

# Blacklisted URL patterns that are traps
BLACKLIST_PATTERNS = [
    r"wics\.ics\.uci\.edu/events/.*",    # wics events trap
    r"wics\.ics\.uci\.edu/event/",       # wics event trap
    r"archive\.ics\.uci\.edu/dataset.*", # archive trap
    r"wiki\.ics\.uci\.edu/doku\.php",    # wiki trap Edwin found
    r"share=",                           # blocks ?share=facebook, ?share=twitter etc.
    r"ical=",                            # blocks calendar export URLs
    r"outlook-ical",                     # blocks outlook calendar URLs
    r"archive-beta\.ics\.uci\.edu/dataset.*",  # archive-beta dataset trap
    r"order=",                           # sorting parameter trap
    r"do=media",                         # media pages in wiki
    r"tab_details=history",              # history pages in wiki
    r"action=login",                     # login pages
    r"action=register",                  # register pages
    r"/auth/",                           # authentication pages
    r"date=",                            # date-based traps
    r"session=",                         # session traps
    r"sid=",                             # session id traps
    r"/day/\d{4}",                       # day based calendar urls
    r"cdb\.ics\.uci\.edu",               # chemical database
    r"wp-login",                         # WordPress login pages
    r"isg\.ics\.uci\.edu/events/tag/talk",  #talk archives on isg
    r"isg\.ics\.uci\.edu/events/\d",     # date-based isg event URLs
    #r"/\d{4}-\d{2}",                     # YYYY-MM archive URLs
    r"C=[DNMS];O=[AD]",                  # Apache directory sorting
]

def scraper(url, resp):
    links = extract_next_links(url, resp)
    validLinks = [link for link in links if is_valid(link)]
    extract_information(url, resp)

    # TODO: find a better place to call this
    # Save as JSON
    if len(unique_pages) > 0:
        save_as_json()

    return validLinks

def extract_information(url,resp)->None:
    if resp.status != 200 or not resp.raw_response or not resp.raw_response.content: #check for status: 200, and that content exists
        return
    
    content_type = resp.raw_response.headers.get('content-type', '')
    if 'pdf' in content_type.lower():
        return

    bSoup = BeautifulSoup(resp.raw_response.content, 'html.parser')
    text = bSoup.get_text(separator=" ", strip=True)
    words = re.findall(r'[a-zA-Z]+', text)  # fixed: alphanumeric only, avoids punctuation attached to words
    currCount = count_words(words)


    #Low information check
    if currCount < 50:
        return
    
    #Q1 Track unique Pages
    unique_pages.add(url)

    #Q2 Update longest_page
    if currCount > longest_page['word_count']:
        longest_page['url'] = url
        longest_page['word_count'] = currCount

    #Q4 Track unique subdomains
    hostname = urlparse(url).hostname
    if hostname:  # fixed: check hostname is not None before using it
        if hostname not in subdomains:
            subdomains[hostname] = set()
        subdomains[hostname].add(url)

def count_words(text)->int:
    valid_words = [word for word in text if word.lower() not in STOP_WORDS and len(word) > 2] #make a list of all words except stop words
    #Q3 kinda only updates the word freq Counter, TODO need to call COUNTS.most_common(50) at some point somewhere
    COUNTS.update([w.lower() for w in valid_words])  # fixed: lowercase so "The" and "the" are not counted separately
    return len(valid_words)

def extract_next_links(url, resp):
    # Implementation required.
    # url: the URL that was used to get the page
    # resp.url: the actual url of the page
    # resp.status: the status code returned by the server. 200 is OK, you got the page. Other numbers mean that there was some kind of problem.
    # resp.error: when status is not 200, you can check the error here, if needed.
    # resp.raw_response: this is where the page actually is. More specifically, the raw_response has two parts:
    #         resp.raw_response.url: the url, again
    #         resp.raw_response.content: the content of the page!
    # Return a list with the hyperlinks (as strings) scrapped from resp.raw_response.content
    global longest_page
    extractedLinks = []
    if resp.status != 200 or not resp.raw_response or not resp.raw_response.content: #check for status: 200, and that content exists
        return extractedLinks
    
    #check for pdf content-type in header
    content_type = resp.raw_response.headers.get('content-type', '')
    if 'pdf' in content_type.lower():
        return extractedLinks
    

    bSoup = BeautifulSoup(resp.raw_response.content, 'html.parser')
    for aTag in bSoup.find_all('a'): #look through all the <a></a> tags in html
        link = aTag.get('href') #get the link associated from the href in the <a></a> tag
        if link:
            fullUrl = urljoin(resp.url, link) #join original url and href link, urllib's urljoin handles absolute vs relative paths
            cleanUrl, fragment = urldefrag(fullUrl) #remove any fragments from the new combined url, anything after a '#' in a url
            extractedLinks.append(cleanUrl) #adds new url to list
    return extractedLinks

def is_valid(url):
    # Decide whether to crawl this url or not.
    # If you decide to crawl it, return True; otherwise return False.
    # There are already some conditions that return False.
    try:
        parsed = urlparse(url)
        # don't crawl if the protocol isn't http or https
        if parsed.scheme not in set(["http", "https"]):
            return False

        # only crawl approved domains
        allowed_domains = [
            ".ics.uci.edu",
            ".cs.uci.edu",
            ".informatics.uci.edu",
            ".stat.uci.edu",
        ]
        if not any(parsed.netloc.endswith(domain) for domain in allowed_domains):
            return False

        # check blacklist patterns to avoid traps
        for pattern in BLACKLIST_PATTERNS:
            if re.search(pattern, url):
                return False

        # avoid urls with too many query parameters
        query_params = parsed.query.count('&')
        if query_params > 3:
            return False

        if len(url) > 200:
            return False

        #repeating path segments
        segments = [s for s in parsed.path.split('/') if s]
        if len(segments) != len(set(segments)):
            return False

        #deep paths
        if len(segments) > 10:
            return False

        decoded_path = unquote(parsed.path).lower()
        return not re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            + r"|png|tiff?|mid|mp2|mp3|mp4"
            + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            + r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            + r"|epub|dll|cnf|tgz|sha1"
            + r"|thmx|mso|arff|rtf|jar|csv"
            + r"|rm|smil|wmv|swf|wma|zip|rar|gz|mpg|ppsx|apk|nb|ipynb|pps)$", decoded_path)

    except TypeError:
        print ("TypeError for ", parsed)
        raise

def save_as_json(path="results.json"):
    results = {
        "unique_pages": list(unique_pages),
        "longest_page": longest_page,
        "subdomains": {key: list(val) for key, val in subdomains.items()},
        "word_counts": COUNTS.most_common(50),
    }
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
