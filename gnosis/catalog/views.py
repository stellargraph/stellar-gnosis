from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect
from .models import Paper, Person, Dataset, Venue, Comment
from .forms import PaperForm, PersonForm, DatasetForm, VenueForm, CommentForm, PaperImportForm
from .forms import SearchVenuesForm, SearchPapersForm, SearchPeopleForm, SearchDatasetsForm
from django.urls import reverse
from django.http import HttpResponseRedirect
from neomodel import db
from datetime import date
from nltk.corpus import stopwords
import pdb
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from bs4 import BeautifulSoup


#
# Paper Views
#
def get_paper_authors(paper):
    query = "MATCH (:Paper {title: {paper_title}})<--(a:Person) RETURN a"
    results, meta = db.cypher_query(query, dict(paper_title=paper.title))
    if len(results) > 0:
        authors = [Person.inflate(row[0]) for row in results]
    else:
        authors = []
    # pdb.set_trace()
    authors = ['{}. {}'.format(author.first_name[0], author.last_name) for author in authors]

    return authors


def get_paper_venue(paper):
    query = "MATCH (:Paper {title: {paper_title}})--(v:Venue) RETURN v"
    results, meta = db.cypher_query(query, dict(paper_title=paper.title))
    if len(results) == 1:  # there should only be one venue associated with a paper
        venue = [Venue.inflate(row[0]) for row in results][0]
    else:
        venue = None
    # pdb.set_trace()
    if venue is not None:
        return '{}, {}'.format(venue.name, venue.publication_date)
    else:
        return ''


def papers(request):
    # Retrieve the papers ordered by newest addition to DB first.
    # limit to maximum 10 papers until we get pagination to work.
    # However, even with pagination, we are going to want to limit
    # the number of papers retrieved for speed, especially when the
    # the DB grows large.
    all_papers = Paper.nodes.order_by('-created')[:10]
    # Retrieve all comments about this paper.
    all_authors = [', '.join(get_paper_authors(paper)) for paper in all_papers]
    all_venues = [get_paper_venue(paper) for paper in all_papers]

    papers = list(zip(all_papers, all_authors, all_venues))

    return render(request,
                  'papers.html',
                  {'papers': papers,
                   'papers_only': all_papers,
                   'num_papers': len(Paper.nodes.all())})


def paper_detail(request, id):
    # Retrieve the paper from the database
    query = "MATCH (a) WHERE ID(a)={id} RETURN a"
    results, meta = db.cypher_query(query, dict(id=id))
    if len(results) > 0:
        all_papers = [Paper.inflate(row[0]) for row in results]
        paper = all_papers[0]
    else:  # go back to the paper index page
        return render(request, 'papers.html', {'papers': Paper.nodes.all(), 'num_papers': len(Paper.nodes.all())})

    # Retrieve all comments about this paper.
    query = "MATCH (:Paper {title: {paper_title}})<--(c:Comment) RETURN c"
    results, meta = db.cypher_query(query, dict(paper_title=paper.title))
    if len(results) > 0:
        comments = [Comment.inflate(row[0]) for row in results]
        num_comments = len(comments)
    else:
        comments = []
        num_comments = 0

    # Retrieve venue where paper was published.
    query = "MATCH (:Paper {title: {paper_title}})-->(v:Venue) RETURN v"
    results, meta = db.cypher_query(query, dict(paper_title=paper.title))
    if len(results) > 0:
        venues = [Venue.inflate(row[0]) for row in results]
        venue = venues[0]
    else:
        venue = None

    request.session['last-viewed-paper'] = id
    return render(request,
                  'paper_detail.html',
                  {'paper': paper, 'venue': venue, 'comments': comments, 'num_comments': num_comments})


def paper_find(request):
    message = None
    if request.method == 'POST':
        form = SearchPapersForm(request.POST)
        print("Received POST request")
        if form.is_valid():
            english_stopwords = stopwords.words('english')
            paper_title = form.cleaned_data['paper_title'].lower()
            paper_title_tokens = [w for w in paper_title.split(' ') if not w in english_stopwords]
            paper_query = '(?i).*' + '+.*'.join('(' + w + ')' for w in paper_title_tokens) + '+.*'
            query = "MATCH (p:Paper) WHERE  p.title =~ { paper_query } RETURN p LIMIT 25"
            print("Cypher query string {}".format(query))
            results, meta = db.cypher_query(query, dict( paper_query=paper_query))
            if len(results) > 0:
                print("Found {} matching papers".format(len(results)))
                papers = [Paper.inflate(row[0]) for row in results]
                return render(request, 'paper_results.html', {'papers': papers})
            else:
                message = "No results found. Please try again!"

    elif request.method == 'GET':
        print("Received GET request")
        form = SearchPapersForm()

    return render(request, 'paper_find.html', {'form': form, 'message': message})


@login_required
def paper_connect_venue(request, id):

    if request.method == 'POST':
        form = SearchVenuesForm(request.POST)
        if form.is_valid():
            # search the db for the venue
            # if venue found, then link with paper and go back to paper view
            # if not, ask the user to create a new venue
            english_stopwords = stopwords.words('english')
            venue_name = form.cleaned_data['venue_name'].lower()
            venue_publication_year = form.cleaned_data['venue_publication_year']
            # TO DO: should probably check that data is 4 digits...
            venue_name_tokens = [w for w in venue_name.split(' ') if not w in english_stopwords]
            venue_query = '(?i).*' + '+.*'.join('(' + w + ')' for w in venue_name_tokens) + '+.*'
            query = "MATCH (v:Venue) WHERE v.publication_date =~ '" + venue_publication_year[0:4] + \
                    ".*' AND v.name =~ { venue_query } RETURN v"
            results, meta = db.cypher_query(query, dict(venue_publication_year=venue_publication_year[0:4],
                                                        venue_query=venue_query))
            if len(results) > 0:
                venues = [Venue.inflate(row[0]) for row in results]
                print("Found {} venues that match".format(len(venues)))
                for v in venues:
                    print("\t{}".format(v))

                if len(results) > 1:
                    # ask the user to select one of them
                    return render(request, 'paper_connect_venue.html', {'form': form,
                                                                        'venues': venues,
                                                                        'message': 'Found more than one matching venues. Please narrow your search'})
                else:
                    venue = venues[0]
                    print('Selected Venue: {}'.format(venue))

                # retrieve the paper
                query = "MATCH (a) WHERE ID(a)={id} RETURN a"
                results, meta = db.cypher_query(query, dict(id=id))
                if len(results) > 0:
                    all_papers = [Paper.inflate(row[0]) for row in results]
                    paper = all_papers[0]
                    print("Found paper: {}".format(paper.title))
                    # check if the paper is connect with a venue; if yes, the remove link to
                    # venue before adding link to the new venue
                    query = 'MATCH (p:Paper)-[r:was_published_at]->(v:Venue) where id(p)={id} return v'
                    results, meta = db.cypher_query(query, dict(id=id))
                    if len(results) > 0:
                        venues = [Venue.inflate(row[0]) for row in results]
                        for v in venues:
                            print("Disconnecting from: {}".format(v))
                            paper.was_published_at.disconnect(v)
                            paper.save()
                else:
                    print("Could not find paper!")
                    # should not get here since we started from the actual paper...but what if we do end up here?
                    pass  # Should raise an exception but for now just pass
                # we have a venue and a paper, so connect them.
                paper.was_published_at.connect(venue)
                return HttpResponseRedirect(reverse('papers_index'))
            else:
                # render new Venue form with the searched name as
                message = 'No matching venues found'

    if request.method == 'GET':
        form = SearchVenuesForm()
        message = None

    return render(request, 'paper_connect_venue.html', {'form': form, 'venues': None, 'message': message})


@login_required
def paper_connect_author(request, id):

    if request.method == 'POST':
        form = SearchPeopleForm(request.POST)
        if form.is_valid():
            # search the db for the person
            # if the person is found, then link with paper and go back to paper view
            # if not, ask the user to create a new person
            name = form.cleaned_data['person_name']
            people_found = _person_find(name)

            if people_found is not None:
                print("Found {} people that match".format(len(people_found)))
                for person in people_found:
                    print("\t{} {} {}".format(person.first_name, person.middle_name, person.last_name))

                if len(people_found) > 1:
                    # ask the user to select one of them
                    return render(request, 'paper_connect_author.html', {'form': form,
                                                                        'people': people_found,
                                                                        'message': 'Found more than one matching people. Please narrow your search'})
                else:
                    person = people_found[0]  # one person found
                    print('Selected person: {} {} {}'.format(person.first_name, person.middle_name, person.last_name))

                # retrieve the paper
                query = "MATCH (a) WHERE ID(a)={id} RETURN a"
                results, meta = db.cypher_query(query, dict(id=id))
                if len(results) > 0:
                    all_papers = [Paper.inflate(row[0]) for row in results]
                    paper = all_papers[0]
                    print("Found paper: {}".format(paper.title))
                    # check if the paper is connect with a venue; if yes, the remove link to
                    # venue before adding link to the new venue
                    query = 'MATCH (p:Paper)<-[r:authors]-(p:Person) where id(p)={id} return p'
                    results, meta = db.cypher_query(query, dict(id=id))
                    if len(results) == 0:
                        # person is not linked with paper so add the edge
                        person.authors.connect(paper)
                        # people = [Person.inflate(row[0]) for row in results]
                        # for p in people:
                        #     print("Disconnecting from: {}".format(p))
                        #     paper.was_published_at.disconnect(p)
                        #     paper.save()
                else:
                    print("Could not find paper!")
                    # should not get here since we started from the actual paper...but what if we do end up here?
                    pass  # Should raise an exception but for now just pass
                # we have a venue and a paper, so connect them.
                return HttpResponseRedirect(reverse('papers_index'))
            else:
                # render new Venue form with the searched name as
                message = 'No matching people found'

    if request.method == 'GET':
        form = SearchPeopleForm()
        message = None

    return render(request, 'paper_connect_author.html', {'form': form, 'people': None, 'message': message})


@login_required
def paper_update(request, id):
    # retrieve paper by ID
    # https://github.com/neo4j-contrib/neomodel/issues/199
    query = "MATCH (a) WHERE ID(a)={id} RETURN a"
    results, meta = db.cypher_query(query, dict(id=id))
    if len(results) > 0:
        all_papers = [Paper.inflate(row[0]) for row in results]
        paper_inst = all_papers[0]
    else:
        paper_inst = Paper()

    # if this is POST request then process the Form data
    if request.method == 'POST':

        form = PaperForm(request.POST)
        if form.is_valid():
            paper_inst.title = form.cleaned_data['title']
            paper_inst.abstract = form.cleaned_data['abstract']
            paper_inst.keywords = form.cleaned_data['keywords']
            paper_inst.download_link = form.cleaned_data['download_link']
            paper_inst.save()

            return HttpResponseRedirect(reverse('papers_index'))
    # GET request
    else:
        query = "MATCH (a) WHERE ID(a)={id} RETURN a"
        results, meta = db.cypher_query(query, dict(id=id))
        if len(results) > 0:
            all_papers = [Paper.inflate(row[0]) for row in results]
            paper_inst = all_papers[0]
        else:
            paper_inst = Paper()
        # paper_inst = Paper()
        form = PaperForm(initial={'title': paper_inst.title,
                                  'abstract': paper_inst.abstract,
                                  'keywords': paper_inst.keywords,
                                  'download_link': paper_inst.download_link, })

    return render(request, 'paper_update.html', {'form': form, 'paper': paper_inst})


def _find_paper(query_string):
    """
    Helper method to query the DB for a paper based on its title.
    :param query_string: The query string, e.g., title of paper to search for
    :return: <list> List of papers that match the query or empty list if none match.
    """
    papers = []
    # Check if paper already exists in DB and only add it if it does not.
    english_stopwords = stopwords.words('english')
    paper_title = query_string.lower()
    paper_title_tokens = [w for w in paper_title.split(' ') if not w in english_stopwords]
    paper_query = '(?i).*' + '+.*'.join('(' + w + ')' for w in paper_title_tokens) + '+.*'
    query = "MATCH (p:Paper) WHERE  p.title =~ { paper_query } RETURN p LIMIT 25"
    print("Cypher query string {}".format(query))
    results, meta = db.cypher_query(query, dict(paper_query=paper_query))
    if len(results) > 0:
        papers = [Paper.inflate(row[0]) for row in results]

    return papers


def _add_author(author, paper=None):
    """
    Adds author to the DB if author does not already exist and links to paper
    as author if paper is not None
    :param author:
    :param paper:
    """
    link_with_paper =False
    p = None
    people_found = _person_find(author, exact_match=True)
    author_name = author.strip().split(' ')
    if people_found is None:  # not in DB
        print("Author {} not in DB".format(author))
        p = Person()
        p.first_name = author_name[0]
        if len(author_name) > 2:  # has middle name(s)
            p.middle_name = author_name[1:-1]
        else:
            p.middle_name = None
        p.last_name = author_name[-1]
        p.save()  # save to DB
        link_with_paper = True
    elif len(people_found) == 1:
        # Exactly one person found. Check if name is an exact match.
        p = people_found[0]
        # NOTE: The problem with this simple check is that if two people have
        # the same name then the wrong person will be linked to the paper.
        if p.first_name == author_name[0] and p.last_name == author_name[-1]:
            if len(author_name) > 2:
                if p.middle_name == author_name[1:-1]:
                    link_with_paper = True
            else:
                link_with_paper = True
    else:
        print("Person with similar but not exactly the same name is already in DB.")

    if link_with_paper and paper is not None:
        print("Adding authors link to paper {}".format(paper.title[:50]))
        # link author with paper
        p.authors.connect(paper)


@login_required
def paper_create(request):
    user = request.user
    print("In paper_create() view.")
    message = ''
    if request.method == 'POST':
        print("   POST")
        paper = Paper()
        paper.created_by = user.id
        form = PaperForm(instance=paper, data=request.POST)
        if form.is_valid():
            # Check if the paper already exists in DB
            matching_papers = _find_paper(form.cleaned_data['title'])
            if len(matching_papers) > 0:  # paper in DB already
                message = "Paper already exists in Gnosis!"
                return render(request, 'paper_results.html', {'papers': matching_papers, 'message': message})
            else:  # the paper is not in DB yet.
                form.save()  # store
                # Now, add the authors and link each author to the paper with an "authors"
                # type edge.
                if request.session['from_arxiv']:
                    paper_authors = request.session['arxiv_authors']
                    for paper_author in paper_authors.split(','):
                        print("Adding author {}".format(paper_author))
                        _add_author(paper_author, paper)

                request.session['from_arxiv'] = False  # reset
                # go back to paper index page.
                # Should this redirect to the page of the new paper just added?
                return HttpResponseRedirect(reverse('papers_index'))
    else:  # GET
        print("   GET")
        # check if this is a redirect from paper_create_from_arxiv
        # if so, then pre-populate the form with the data from arXiv,
        # otherwise start with an empty form.
        if request.session['from_arxiv'] is True:
            title = request.session['arxiv_title']
            abstract = request.session['arxiv_abstract']
            url = request.session['arxiv_url']

            form = PaperForm(initial={'title': title,
                                      'abstract': abstract,
                                      'download_link': url})
        else:
            form = PaperForm()

    return render(request, 'paper_form.html', {'form': form, 'message': message})


def get_authors(bs4obj):
    """
    Extract authors from arXiv.org paper page
    :param bs4obj:
    :return: None or a string with comma separated author names from first to last name
    """
    authorList = bs4obj.findAll("div", {"class": "authors"})
    if authorList is not None:
        if len(authorList) > 1:
            # there should be just one but let's just take the first one
            authorList = authorList[0]

        # for author in authorList:
        # print("type of author {}".format(type(author)))
        author_str = authorList[0].get_text()
        if author_str.startswith("Authors:"):
            author_str = author_str[8:]
        return author_str
    # authorList is None so return None
    return None


def get_title(bs4obj):
    """
    Extract paper title from arXiv.org paper page.
    :param bs4obj:
    :return:
    """
    titleList = bs4obj.findAll("h1", {"class": "title"})
    if titleList is not None:
        if len(titleList) == 0:
            return None
        else:
            if len(titleList) > 1:
                print("WARNING: Found more than one title. Returning the first one.")
            #return " ".join(titleList[0].get_text().split()[1:])
            title_text = titleList[0].get_text()
            if title_text.startswith('Title:'):
                return title_text[6:]
            else:
                return title_text
    return None


def get_abstract(bs4obj):
    """
    Extract paper abstract from arXiv.org paper page.
    :param bs4obj:
    :return:
    """
    abstract = bs4obj.find("blockquote", {"class": "abstract"})
    if abstract is not None:
        abstract = " ".join(abstract.get_text().split(' ')[1:])
    return abstract


def get_venue(bs4obj):
    """
    Extract publication venue from arXiv.org paper page.
    :param bs4obj:
    :return:
    """
    venue = bs4obj.find("td", {"class": "tablecell comments mathjax"})
    if venue is not None:
        venue = venue.get_text().split(';')[0]
    return venue


def get_paper_info(url):
    """
    Extract paper information, title, abstract, and authors, from arXiv.org
    paper page.
    :param url:
    :return:
    """
    try:
        # html = urlopen("http://pythonscraping.com/pages/page1.html")
        html = urlopen(url)
    except HTTPError as e:
        print(e)
    except URLError as e:
        print(e)
        print("The server could not be found.")
    else:
        bs4obj = BeautifulSoup(html)
        # Now, we can access individual element in the page
        authors = get_authors(bs4obj)
        title = get_title(bs4obj)
        abstract = get_abstract(bs4obj)
        # venue = get_venue(bs4obj)
        return title, authors, abstract

    return None, None, None


@login_required
def paper_create_from_arxiv(request):
    user = request.user

    if request.method == 'POST':
        # create the paper from the extracted data and send to
        # paper_form.html asking the user to verify
        print("{}".format(request.POST['url']))
        # get the data from arxiv
        url = request.POST['url']
        # check if url includes https, and if not add it
        if not url.startswith("https://"):
            url = "https://"+url
        # retrieve paper info. If the information cannot be retrieved from remote
        # server, then we will return an error message and redirect to paper_form.html.
        title, authors, abstract = get_paper_info(url)
        if title is None or authors is None or abstract is None:
            form = PaperImportForm()
            return render(request, 'paper_form.html', {'form': form, 'message': "Invalid source, please try again."})

        request.session['from_arxiv'] = True
        request.session['arxiv_title'] = title
        request.session['arxiv_abstract'] = abstract
        request.session['arxiv_url'] = url
        request.session['arxiv_authors'] = authors  # comma separate list of author names, first to last name

        print("Authors: {}".format(authors))

        return HttpResponseRedirect(reverse('paper_create'))
    else:  # GET
        request.session['from_arxiv'] = False
        form = PaperImportForm()

    return render(request, 'paper_form.html', {'form': form})


def _person_find(person_name, exact_match=False):
    """
    Searches the DB for a person whose name matches the given name
    :param person_name:
    :return:
    """
    person_name = person_name.lower()
    person_name_tokens = [w for w in person_name.split()]
    if exact_match:
        if len(person_name_tokens) > 2:
            query = ("MATCH (p:Person) WHERE  LOWER(p.last_name) IN { person_tokens } AND LOWER(p.first_name) IN { person_tokens } AND LOWER(p.middle_name) IN { person_tokens } RETURN p LIMIT 20")
        else:
            query = ("MATCH (p:Person) WHERE  LOWER(p.last_name) IN { person_tokens } AND LOWER(p.first_name) IN { person_tokens } RETURN p LIMIT 20")
    else:
        query = "MATCH (p:Person) WHERE  LOWER(p.last_name) IN { person_tokens } OR LOWER(p.first_name) IN { person_tokens } OR LOWER(p.middle_name) IN { person_tokens } RETURN p LIMIT 20"

    results, meta = db.cypher_query(query, dict(person_tokens=person_name_tokens))

    if len(results) > 0:
        print("Found {} matching people".format(len(results)))
        people = [Person.inflate(row[0]) for row in results]
        return people
    else:
        return None


def person_find(request):
    """
    Searching for a person in the DB.

    :param request:
    :return:
    """
    message = None
    if request.method == 'POST':
        form = SearchPeopleForm(request.POST)
        print("Received POST request")
        if form.is_valid():

            people = _person_find(form.cleaned_data['person_name'])
            if people is not None:
                return render(request, 'people.html', {'people': people})
            else:
                message = "No results found. Please try again!"

    elif request.method == 'GET':
        print("Received GET request")
        form = SearchPeopleForm()

    return render(request, 'person_find.html', {'form': form, 'message': message})


#
# Person Views
#
def persons(request):
    return render(request, 'people.html', {'people': Person.nodes.all(), 'num_people': len(Person.nodes.all())})


def person_detail(request, id):
    # Retrieve the paper from the database
    query = "MATCH (a) WHERE ID(a)={id} RETURN a"
    results, meta = db.cypher_query(query, dict(id=id))
    if len(results) > 0:
        # There should be only one results because ID should be unique. Here we check that at
        # least one result has been returned and take the first result as the correct match.
        # Now, it should not happen that len(results) > 1 since IDs are meant to be unique.
        # For the MVP we are going to ignore the latter case and just continue but ultimately,
        # we should be checking for > 1 and failing gracefully.
        all_people = [Person.inflate(row[0]) for row in results]
        person = all_people[0]
    else:  # go back to the paper index page
        return render(request, 'people.html', {'people': Person.nodes.all(), 'num_people': len(Person.nodes.all())})

    #
    # TO DO: Retrieve all papers co-authored by this person and list them; same for
    # co-authors and advisees.
    #
    request.session['last-viewed-person'] = id
    return render(request,
                  'person_detail.html',
                  {'person': person})


@login_required
def person_create(request):
    user = request.user

    if request.method == 'POST':
        person = Person()
        person.created_by = user.id
        form = PersonForm(instance=person, data=request.POST)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('persons_index'))
    else:  # GET
        form = PersonForm()

    return render(request, 'person_form.html', {'form': form})


@login_required
def person_update(request, id):
    # retrieve paper by ID
    # https://github.com/neo4j-contrib/neomodel/issues/199
    query = "MATCH (a) WHERE ID(a)={id} RETURN a"
    results, meta = db.cypher_query(query, dict(id=id))
    if len(results) > 0:
        all_people = [Person.inflate(row[0]) for row in results]
        person_inst = all_people[0]
    else:
        person_inst = Person()

    # if this is POST request then process the Form data
    if request.method == 'POST':
        form = PersonForm(request.POST)
        if form.is_valid():
            person_inst.first_name = form.cleaned_data['first_name']
            person_inst.middle_name = form.cleaned_data['middle_name']
            person_inst.last_name = form.cleaned_data['last_name']
            person_inst.affiliation = form.cleaned_data['affiliation']
            person_inst.website = form.cleaned_data['website']
            person_inst.save()

            return HttpResponseRedirect(reverse('persons_index'))
    # GET request
    else:
        query = "MATCH (a) WHERE ID(a)={id} RETURN a"
        results, meta = db.cypher_query(query, dict(id=id))
        if len(results) > 0:
            all_people = [Person.inflate(row[0]) for row in results]
            person_inst = all_people[0]
        else:
            person_inst = Person()
        form = PersonForm(initial={'first_name': person_inst.first_name,
                                   'middle_name': person_inst.middle_name,
                                   'last_name': person_inst.last_name,
                                   'affiliation': person_inst.affiliation,
                                   'website': person_inst.website,
                                   }
                          )

    return render(request, 'person_update.html', {'form': form, 'person': person_inst})


#
# Dataset Views
#
def datasets(request):
    all_datasets = Dataset.nodes.order_by('-publication_date')[:10]
    return render(request, 'datasets.html', {'datasets': all_datasets})


def dataset_detail(request, id):
    # Retrieve the paper from the database
    query = "MATCH (a) WHERE ID(a)={id} RETURN a"
    results, meta = db.cypher_query(query, dict(id=id))
    if len(results) > 0:
        # There should be only one results because ID should be unique. Here we check that at
        # least one result has been returned and take the first result as the correct match.
        # Now, it should not happen that len(results) > 1 since IDs are meant to be unique.
        # For the MVP we are going to ignore the latter case and just continue but ultimately,
        # we should be checking for > 1 and failing gracefully.
        all_datasets = [Dataset.inflate(row[0]) for row in results]
        dataset = all_datasets[0]
    else:  # go back to the paper index page
        return render(request, 'datasets.html',
                      {'datasets': Dataset.nodes.all(), 'num_datasets': len(Dataset.nodes.all())})

    #
    # TO DO: Retrieve and list all papers that evaluate on this dataset.
    #

    request.session['last-viewed-dataset'] = id

    return render(request,
                  'dataset_detail.html',
                  {'dataset': dataset})


def dataset_find(request):
    """
    Searching for a dataset in the DB.

    :param request:
    :return:
    """
    message = None
    if request.method == 'POST':
        form = SearchDatasetsForm(request.POST)
        print("Received POST request")
        if form.is_valid():
            dataset_name = form.cleaned_data['name'].lower()
            dataset_keywords = form.cleaned_data['keywords'].lower()  # comma separated list
            dataset_name_tokens = [w for w in dataset_name.split()]
            dataset_keywords = [w for w in dataset_keywords.split()]

            if len(dataset_keywords) > 0 and len(dataset_name_tokens) > 0:
                keyword_query = '(?i).*' + '+.*'.join('(' + w + ')' for w in dataset_keywords) + '+.*'
                name_query = '(?i).*' + '+.*'.join('(' + w + ')' for w in dataset_name_tokens) + '+.*'
                query = "MATCH (d:Dataset) WHERE  d.name =~ { name_query } AND d.keywords =~ { keyword_query} RETURN d LIMIT 25"
                results, meta = db.cypher_query(query, dict(name_query=name_query, keyword_query=keyword_query))
                if len(results) > 0:
                    datasets = [Dataset.inflate(row[0]) for row in results]
                    return render(request, 'datasets.html', {'datasets': datasets})
                else:
                    message = "No results found. Please try again!"
            else:
                if len(dataset_keywords) > 0:
                    # only keywords given
                    dataset_query = '(?i).*' + '+.*'.join('(' + w + ')' for w in dataset_keywords) + '+.*'
                    query = "MATCH (d:Dataset) WHERE  d.keywords =~ { dataset_query } RETURN d LIMIT 25"
                else:
                    # only name or nothing (will still return all datasets if name and
                    # keywords fields are left empty and sumbit button is pressed.
                    dataset_query = '(?i).*' + '+.*'.join('(' + w + ')' for w in dataset_name_tokens) + '+.*'
                    query = "MATCH (d:Dataset) WHERE  d.name =~ { dataset_query } RETURN d LIMIT 25"
                    # results, meta = db.cypher_query(query, dict(dataset_query=dataset_query))

                results, meta = db.cypher_query(query, dict(dataset_query=dataset_query))
                if len(results) > 0:
                    datasets = [Dataset.inflate(row[0]) for row in results]
                    return render(request, 'datasets.html', {'datasets': datasets})
                else:
                    message = "No results found. Please try again!"
    elif request.method == 'GET':
        print("Received GET request")
        form = SearchDatasetsForm()

    return render(request, 'dataset_find.html', {'form': form, 'message': message})


@login_required
def dataset_create(request):
    user = request.user

    if request.method == 'POST':
        dataset = Dataset()
        dataset.created_by = user.id
        form = DatasetForm(instance=dataset, data=request.POST)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('datasets_index'))
    else:  # GET
        form = DatasetForm()

    return render(request, 'dataset_form.html', {'form': form})


@login_required
def dataset_update(request, id):
    # retrieve paper by ID
    # https://github.com/neo4j-contrib/neomodel/issues/199
    query = "MATCH (a) WHERE ID(a)={id} RETURN a"
    results, meta = db.cypher_query(query, dict(id=id))
    if len(results) > 0:
        datasets = [Dataset.inflate(row[0]) for row in results]
        dataset = datasets[0]
    else:
        dataset = Dataset()

    # if this is POST request then process the Form data
    if request.method == 'POST':
        form = DatasetForm(request.POST)
        if form.is_valid():
            dataset.name = form.cleaned_data['name']
            dataset.keywords = form.cleaned_data['keywords']
            dataset.description = form.cleaned_data['description']
            dataset.publication_date = form.cleaned_data['publication_date']
            dataset.source_type = form.cleaned_data['source_type']
            dataset.website = form.cleaned_data['website']
            dataset.save()

            return HttpResponseRedirect(reverse('datasets_index'))
    # GET request
    else:
        query = "MATCH (a) WHERE ID(a)={id} RETURN a"
        results, meta = db.cypher_query(query, dict(id=id))
        if len(results) > 0:
            datasets = [Dataset.inflate(row[0]) for row in results]
            dataset = datasets[0]
        else:
            dataset = Dataset()
        form = DatasetForm(initial={'name': dataset.name,
                                    'keywords': dataset.keywords,
                                    'description': dataset.description,
                                    'publication_date': dataset.publication_date,
                                    'source_type': dataset.source_type,
                                    'website': dataset.website,
                                    }
                           )

    return render(request, 'dataset_update.html', {'form': form, 'dataset': dataset})


#
# Venue Views
#
def venues(request):
    all_venues = Venue.nodes.order_by('-publication_date')[: 10]
    return render(request, 'venues.html', {'venues': all_venues})


def venue_detail(request, id):
    # Retrieve the paper from the database
    query = "MATCH (a) WHERE ID(a)={id} RETURN a"
    results, meta = db.cypher_query(query, dict(id=id))
    if len(results) > 0:
        # There should be only one results because ID should be unique. Here we check that at
        # least one result has been returned and take the first result as the correct match.
        # Now, it should not happen that len(results) > 1 since IDs are meant to be unique.
        # For the MVP we are going to ignore the latter case and just continue but ultimately,
        # we should be checking for > 1 and failing gracefully.
        all_venues = [Venue.inflate(row[0]) for row in results]
        venue = all_venues[0]
    else:  # go back to the paper index page
        return render(request, 'venues.html', {'venues': Venue.nodes.all(), 'num_venues': len(Venue.nodes.all())})

    #
    # TO DO: Retrieve all papers published at this venue and list them
    #
    request.session['last-viewed-venue'] = id
    return render(request,
                  'venue_detail.html',
                  {'venue': venue})


def venue_find(request):
    """
    Search for venue.
    :param request:
    :return:
    """
    if request.method == 'POST':
        form = SearchVenuesForm(request.POST)
        if form.is_valid():
            # search the db for the venue
            # if venue found, then link with paper and go back to paper view
            # if not, ask the user to create a new venue
            english_stopwords = stopwords.words('english')
            venue_name = form.cleaned_data['venue_name'].lower()
            venue_publication_year = form.cleaned_data['venue_publication_year']
            # TO DO: should probably check that data is 4 digits...
            venue_name_tokens = [w for w in venue_name.split(' ') if not w in english_stopwords]
            venue_query = '(?i).*' + '+.*'.join('(' + w + ')' for w in venue_name_tokens) + '+.*'
            query = "MATCH (v:Venue) WHERE v.publication_date =~ '" + venue_publication_year[0:4] + \
                    ".*' AND v.name =~ { venue_query } RETURN v"
            results, meta = db.cypher_query(query, dict(venue_publication_year=venue_publication_year[0:4],
                                                        venue_query=venue_query))
            if len(results) > 0:
                venues = [Venue.inflate(row[0]) for row in results]
                print("Found {} venues that match".format(len(venues)))
                return render(request, 'venues.html', {'venues': venues})
            else:
                # render new Venue form with the searched name as
                message = 'No matching venues found'

    if request.method == 'GET':
        form = SearchVenuesForm()
        message = None

    return render(request, 'venue_find.html', {'form': form, 'message': message})


@login_required
def venue_create(request):
    user = request.user

    if request.method == 'POST':
        venue = Venue()
        venue.created_by = user.id
        form = VenueForm(instance=venue, data=request.POST)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('venues_index'))
    else:  # GET
        form = VenueForm()

    return render(request, 'venue_form.html', {'form': form})


@login_required
def venue_update(request, id):
    # retrieve paper by ID
    # https://github.com/neo4j-contrib/neomodel/issues/199
    query = "MATCH (a) WHERE ID(a)={id} RETURN a"
    results, meta = db.cypher_query(query, dict(id=id))
    if len(results) > 0:
        venues = [Venue.inflate(row[0]) for row in results]
        venue = venues[0]
    else:
        venue = Venue()

    # if this is POST request then process the Form data
    if request.method == 'POST':
        form = VenueForm(request.POST)
        if form.is_valid():
            venue.name = form.cleaned_data['name']
            venue.publication_date = form.cleaned_data['publication_date']
            venue.type = form.cleaned_data['type']
            venue.publisher = form.cleaned_data['publisher']
            venue.keywords = form.cleaned_data['keywords']
            venue.peer_reviewed = form.cleaned_data['peer_reviewed']
            venue.website = form.cleaned_data['website']
            venue.save()

            return HttpResponseRedirect(reverse('venues_index'))
    # GET request
    else:
        query = "MATCH (a) WHERE ID(a)={id} RETURN a"
        results, meta = db.cypher_query(query, dict(id=id))
        if len(results) > 0:
            venues = [Venue.inflate(row[0]) for row in results]
            venue = venues[0]
        else:
            venue = Venue()
        form = VenueForm(initial={'name': venue.name,
                                  'type': venue.type,
                                  'publication_date': venue.publication_date,
                                  'publisher': venue.publisher,
                                  'keywords': venue.keywords,
                                  'peer_reviewed': venue.peer_reviewed,
                                  'website': venue.website,
                                  }
                         )

    return render(request, 'venue_update.html', {'form': form, 'venue': venue})


#
# Comment Views
#
@login_required
def comments(request):
    """
    We should only show the list of comments if the user is admin. Otherwise, the user should
    be redirected to the home page.
    :param request:
    :return:
    """
    # Only superusers can view all the comments
    if request.user.is_superuser:
        return render(request, 'comments.html', {'comments': Comment.nodes.all(), 'num_comments': len(Comment.nodes.all())})
    else:
        # other users are sent back to the paper index
        return HttpResponseRedirect(reverse('papers_index'))


@login_required
def comment_detail(request, id):
    # Only superusers can view comment details.
    if request.user.is_superuser:
        return render(request, 'comment_detail.html', {'comment': Comment.nodes.all()})
    else:
        # other users are sent back to the papers index
        return HttpResponseRedirect(reverse('papers_index'))


@login_required
def comment_create(request):
    user = request.user

    # Retrieve paper using paper id
    paper_id = request.session['last-viewed-paper']
    query = "MATCH (a) WHERE ID(a)={id} RETURN a"
    results, meta = db.cypher_query(query, dict(id=paper_id))
    if len(results) > 0:
        all_papers = [Paper.inflate(row[0]) for row in results]
        paper = all_papers[0]
    else:  # just send him to the list of papers
        HttpResponseRedirect(reverse('papers_index'))

    if request.method == 'POST':
        comment = Comment()
        comment.created_by = user.id
        comment.author = user.username
        form = CommentForm(instance=comment, data=request.POST)
        if form.is_valid():
            # add link from new comment to paper
            form.save()
            comment.discusses.connect(paper)
            del request.session['last-viewed-paper']
            return redirect('paper_detail', id=paper_id)
    else:  # GET
        form = CommentForm()

    return render(request, 'comment_form.html', {'form': form})


@login_required
def comment_update(request, id):
    # retrieve paper by ID
    # https://github.com/neo4j-contrib/neomodel/issues/199
    query = "MATCH (a) WHERE ID(a)={id} RETURN a"
    results, meta = db.cypher_query(query, dict(id=id))
    if len(results) > 0:
        comments = [Comment.inflate(row[0]) for row in results]
        comment = comments[0]
    else:
        comment = Comment()

    # Retrieve paper using paper id
    paper_id = request.session['last-viewed-paper']

    # if this is POST request then process the Form data
    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment.text = form.cleaned_data['text']
            # comment.author = form.cleaned_data['author']
            comment.save()
            # return HttpResponseRedirect(reverse('comments_index'))
            del request.session['last-viewed-paper']
            return redirect('paper_detail', id=paper_id)

    # GET request
    else:
        query = "MATCH (a) WHERE ID(a)={id} RETURN a"
        results, meta = db.cypher_query(query, dict(id=id))
        if len(results) > 0:
            comments = [Comment.inflate(row[0]) for row in results]
            comment = comments[0]
        else:
            comment = Comment()
        # form = CommentForm(initial={'author': comment.author,
        #                             'text': comment.text,
        #                             'publication_date': comment.publication_date,
        #                             }
        #                    )
        form = CommentForm(initial={'text': comment.text,
                                    'publication_date': comment.publication_date,
                                    }
                           )

    return render(request, 'comment_update.html', {'form': form, 'comment': comment})


#
# Utility Views (admin required)
#
@login_required
def build(request):

    try:
        d1 = Dataset()
        d1.name = 'Yelp'
        d1.source_type = 'N'
        d1.save()

        v1 = Venue()
        v1.name = 'Neural Information Processing Systems'
        v1.publication_date = date(2017, 12, 15)
        v1.type = 'C'
        v1.publisher = 'NIPS Foundation'
        v1.keywords = 'machine learning, machine learning, computational neuroscience'
        v1.website = 'https://nips.cc'
        v1.peer_reviewed = 'Y'
        v1.save()

        v2 = Venue()
        v2.name = 'International Conference on Machine Learning'
        v2.publication_date = date(2016, 5, 24)
        v2.type = 'C'
        v2.publisher = 'International Machine Learning Society (IMLS)'
        v2.keywords = 'machine learning, computer science'
        v2.peer_reviewed = 'Y'
        v2.website = 'https://icml.cc/2016/'
        v2.save()


        p1 = Paper()
        p1.title = 'The best paper in the world.'
        p1.abstract = 'Abstract goes here'
        p1.keywords = 'computer science, machine learning, graphs'
        p1.save()

        p1.evaluates_on.connect(d1)
        p1.was_published_at.connect(v1)

        p2 = Paper()
        p2.title = 'The second best paper in the world.'
        p2.abstract = 'Abstract goes here'
        p2.keywords = 'statistics, robust methods'
        p2.save()

        p2.cites.connect(p1)
        p2.was_published_at.connect(v2)

        p3 = Paper()
        p3.title = 'I wish I could write a paper with a great title.'
        p3.abstract = 'Abstract goes here'
        p3.keywords = 'machine learning, neural networks, convolutional neural networks'
        p3.save()

        p3.cites.connect(p1)
        p3.was_published_at.connect(v1)

        a1 = Person()
        a1.first_name = 'Pantelis'
        a1.last_name = 'Elinas'
        a1.save()

        a1.authors.connect(p1)

        a2 = Person()
        a2.first_name = "Ke"
        a2.last_name = "Sun"
        a2.save()

        a2.authors.connect(p1)
        a2.authors.connect(p2)

        a3 = Person()
        a3.first_name = "Bill"
        a3.last_name = "Gates"
        a3.save()

        a3.authors.connect(p3)
        a3.advisor_of.connect(a1)

        a4 = Person()
        a4.first_name = "Steve"
        a4.last_name = "Jobs"
        a4.save()

        a4.authors.connect(p2)
        a4.authors.connect(p3)

        a4.co_authors_with.connect(a3)

        c1 = Comment()
        c1.author = "Pantelis Elinas"
        c1.text = "This paper is flawless"
        c1.save()

        c1.discusses.connect(p1)

    except Exception:
        pass

    num_papers = len(Paper.nodes.all())
    num_people = len(Person.nodes.all())

    return render(request, 'build.html', {'num_papers': num_papers, 'num_people': num_people})


