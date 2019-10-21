#!/usr/bin/env python3

from flask import Flask, abort, render_template, request, make_response, redirect, url_for
import json, sys, urllib
import logging

from miscellaneous import *
import auth
import lang
import design
import config
from balloon import Balloon
from db import DB

ball = Flask(__name__)
actions = {}


def page(*, title, content):
    return render_template(
        'template.html',
        title=title,
        base=config.base_url,
        content=content
    )


# actions: methods that modify something

@arguments(None, id=int)
def action_access_grant(db, *, id):
    db.volunteer_access(id, True)
    return redirect(url_for('volunteers'))

@arguments(None, id=int)
def action_access_refuse(db, *, id):
    db.volunteer_access(id, False)
    return redirect(url_for('volunteers'))

@arguments(None, url=str)
def action_event_add(db, *, url):
    db.event_add(1, url)
    return redirect(url_for('index'))

@arguments(None, problem=int, value=str)
def action_color_set(db, *, problem, value):
    db.problem_color(problem, value)
    return redirect(url_for("problem", problem=problem))

@arguments(None, event=int, balloon=int, volunteer=str, hall=int)
def action_balloon_done(db, *, event, balloon, volunteer, hall):
    db.balloon_done(balloon, volunteer)
    return redirect(url_for("event", event=event, hall=hall))

@arguments(None, event=int, balloon=int, hall=int)
def action_balloon_drop(db, *, event, balloon, hall):
    db.balloon_drop(balloon)
    return redirect(url_for("event", event=event, hall=hall))

@arguments(None, event=int, balloon=int, volunteer=str, hall=int)
def action_balloon_take(db, *, event, balloon, volunteer, hall):
    balloon = db.balloon(balloon, lock=True)
    if balloon is None:
        return abort(404)
    state = int (balloon[4])
    if state >= 100:
        return redirect(url_for("event", event=event, hall=hall))
    db.balloon_take(balloon[0], volunteer)
    return redirect(url_for("event", event=event, hall=hall))


@ball.route('/action_mk2', methods=['POST'])
def do_action_mk2():
    user_id, auth_html, user_ok = check_auth(request)
    if not user_ok:
        return redirect(url_for('index'), code=307)
    token = request.form['token']
    token_cookie = request.cookies.get('ball_token')
    if token != token_cookie or len(token) < 10:
        print ("token mismatch: %s vs %s" % (repr (token), repr (token_cookie)), file=sys.stderr)
        return abort(403);
    try:
        callback = {
            'access_grant': action_access_grant,
            'access_refuse': action_access_refuse,
            'event_add': action_event_add,
            'color_set': action_color_set,
            'balloon_take': action_balloon_take,
            'balloon_drop': action_balloon_drop,
            'balloon_done': action_balloon_done,
        }[request.form['method']]
    except KeyError:
        print ("unknown action method: '%s'" % request.form['method'])
        return abort(404)
    db = DB()
    result = callback(db, **{
        k: v for k, v in request.form.items()
        if k not in ['method', 'token']
    })
    db.close(commit=True)
    return result


volunteer_cache = {}
def volunteer_get(volunteer_id):
    if volunteer_id in volunteer_cache:
        return volunteer_cache[volunteer_id]
    db = DB()
    name, url = db.volunteer_get(volunteer_id)
    db.close()
    if name:
      volunteer_cache[volunteer_id] = (name, url)
    else:
      volunteer_cache[volunteer_id] = None
    return volunteer_cache[volunteer_id]


@ball.route('/')
def index():
    user_id, auth_html, user_ok = check_auth(request)
    content = ''
    db = DB()
    events = db.events()
    db.close()
    if len(events) == 0:
        content = lang.lang['index_no_events']
    if user_ok:
        event_link = design.event_link
    else:
        event_link = design.event_nolink
    for e in events:
        if e[1]:
            content += event_link(url=url_for('event', event=e[0], hall=0), name=e[1])
        else:
            content += design.event_nolink(name=e[3])
    if user_ok:
        content += design.action_form_event(arguments={
            'method': 'event_add',
        })
        content += design.link(url=url_for('volunteers'), label=lang.lang['access_manage'])
    response = make_response(render_template(
        'template.html',
        title=lang.lang['index_title'],
        auth=auth_html,
        base=config.base_url,
        content=content
    ))
    if user_ok:
        token = auth.create_token(user_id, add_random=True)
        response.set_cookie('ball_token', token)
    return response


@ball.route('/volunteers')
def volunteers():
    user_id, auth_html, user_ok = check_auth(request)
    if not user_ok:
        return redirect(url_for('index'))
    volunteers = []
    for id in config.allowed_users:
        volunteer = volunteer_get(id)
        if volunteer is None:
            volunteer_str = design.volunteer(id=str(id))
        else:
            volunteer_name, volunteer_link = volunteer
            volunteer_str = ' ' + design.volunteer_ext(
                name=volunteer_name,
                url=volunteer_link
            )
        if id == user_id:
            change = design.text(text=lang.lang['this_is_you'])
        else:
            change = design.text(text=lang.lang['volunteer_from_config'])
        volunteers.append(design.volunteer_access(
            name=volunteer_str,
            change=change
        ))
    db = DB()
    for db_id, id, access in db.volunteers():
        if id in config.allowed_users:
          continue
        volunteer = volunteer_get(id)
        if volunteer is None:
            volunteer_str = design.volunteer(id=str(id))
        else:
            volunteer_name, volunteer_link = volunteer
            volunteer_str = ' ' + design.volunteer_ext(
                name=volunteer_name,
                url=volunteer_link
            )
        if id == user_id:
            change = design.text(text=lang.lang['this_is_you'])
        # Only volunteers listed in config file should give permissions.
        # This is insecure solution, other volunteers still can use direct link.
        elif user_id not in config.allowed_users:
            change = ''
        elif access:
            change = design.action_link_mk2(
                arguments={
                    'method': 'access_refuse',
                    'id': db_id
                },
                label=lang.lang['access_refuse']
            )
        else:
            change = design.action_link_mk2(
                arguments={
                    'method': 'access_grant',
                    'id': db_id
                },
                label=lang.lang['access_grant']
            )
        volunteers.append((
            design.volunteer_access if access else design.volunteer_noaccess
        )(
            name=volunteer_str,
            change=change
        ))
    db.close()
    volunteers = ''.join(volunteers)
    content = design.volunteers(volunteers=volunteers)
    response = make_response (render_template(
        'template.html',
        title=lang.lang['volunteers_title'],
        auth=auth_html,
        base=config.base_url,
        content=content
    ))
    token = auth.create_token(user_id, add_random=True)
    response.set_cookie('ball_token', token)
    return response


@ball.route('/problem<int:problem>')
def problem(problem):
    user_id, auth_html, user_ok = check_auth(request)
    if not user_ok:
        return redirect(url_for('index'))
    problem_id = int(problem)
    content = ''
    db = DB()
    problems = [db.problem(problem_id)]
    db.close()
    problems_html = design.problem_header(letter=problems[0]['letter'], name=problems[0]['name'])
    content += problems_html
    colors_html = ''
    colors_html += design.problem_color(color=problems[0]['color'])
    colors_html += design.action_form_color(
        arguments={
            'method': 'color_set',
            'problem': problem_id
        },
        default=problems[0]['color']
    )
    content += colors_html
    response = make_response (render_template(
        'template.html',
        title=problems[0]['letter'],
        auth=auth_html,
        base=config.base_url,
        content=content
    ))
    token = auth.create_token(user_id, add_random=True)
    response.set_cookie('ball_token', token)
    return response


def get_state_str_current(event_id, b, *, user_id, hall):
    state_str = design.action_link_mk2(
        arguments={
            'method': 'balloon_done',
            'event': event_id,
            'balloon': b.id,
            'volunteer': user_id,
            'hall': hall,
        },
        label=lang.lang['event_queue_done']
    ) + ' ' + design.action_link_mk2(
        arguments={
            'method': 'balloon_drop',
            'event': event_id,
            'balloon': b.id,
            'hall': hall,
        },
        label=lang.lang['event_queue_drop']
    )
    return state_str


def get_state_str_queue(event_id, b, *, user_id, hall=0):
    state_str = None
    if b.state >= 0 and b.state < 100:
        state_str = (
            design.text(text=lang.lang['balloon_state_wanted']) + ' ' +
            design.action_link_mk2(
                arguments={
                    'method': 'balloon_take',
                    'event': event_id,
                    'balloon': b.id,
                    'volunteer': user_id,
                    'hall': hall,
                },
                label=lang.lang['event_queue_take']
            )
        )
    elif b.state < 200:
        state_str = design.text(text=lang.lang['balloon_state_carrying'])
    elif b.state < 300:
        state_str = design.text(text=lang.lang['balloon_state_delivered'])
    else:
        state_str = design.text(lang.lang['balloon_state_error'])
    if str(b.volunteer_id) != '':
        volunteer = volunteer_get (str(b.volunteer_id))
        if volunteer is None:
            state_str += ' ' + design.volunteer(id=str(b.volunteer_id))
        else:
            volunteer_name, volunteer_link = volunteer
            state_str += ' ' + design.volunteer_ext(
                name=volunteer_name,
                url=volunteer_link
            )
    return state_str


@ball.route('/event<int:eventp>')
def event_nohall(eventp):
  return event(eventp, 0)

@ball.route('/event<int:event>_<int:hall>')
def event(event, hall):
    user_id, auth_html, user_ok = check_auth(request)
    if not user_ok:
        return redirect(url_for('index'))
    event_id = int(event)
    content = ''
    db = DB()
    try:
        e = db.event(event_id)
    except KeyError:
        e = None
    if e is None:
        return redirect(url_for('index'))
    event = {
        'name': e[1],
        'state': e[2],
        'url': e[3]}
    event_html = ''
    event_html += design.standings_link(url=url_for('event_standings', event=event_id))
    content += event_html
    content += design.halls_list(event_id=event_id, current_hall=hall)

    problems = db.problems(event_id)
    problems_map = {p['id']: i for i, p in enumerate (problems)}
    for p in problems:
        cnt = db.balloons_count(event_id, p['id'])
        p['cnt'] = cnt
    problems_html = design.problems(
        problems=''.join ([
            design.problem(
                color_token='&nbsp;' if p['color'] else '?',
                color=p['color'],
                url=url_for('problem', problem=p['id']),
                letter=p['letter'],
                count=str(p['cnt'])
            )
            for p in problems
        ])
    )
    content += problems_html

    teams = db.teams(event_id)
    teams_map = {t['id']: i for i, t in enumerate (teams)}

    first_to_solve = {}
    for p in problems:
        try:
            first_to_solve[p['id']] = db.fts(event_id, problem_id=p['id'])
        except KeyError:
            pass

    first_solved = {}
    for t in teams:
        try:
            first_solved[t['id']] = db.fts(event_id, team_id=t['id'])
        except KeyError:
            pass

    def get_balloons_html(header, get_state_str, balloons):
        nonlocal user_id
        if len(balloons) == 0:
            return ''
        balloons_html = []
        for b in balloons:
            p = problems[problems_map[b.problem_id]]
            t = teams[teams_map[b.team_id]]
            state_str = get_state_str(event_id, b, user_id=user_id, hall=hall)
            balloons_text = '&nbsp;'
            if not p['color']:
                balloons_text = '?'
            if first_to_solve[b.problem_id] == b.id:
                x = design.fts(text=lang.lang['event_queue_problem'])
            else:
                x = design.fts_no(text=lang.lang['event_queue_problem'])
            # FTS for team is confusing, disable it for now
            #if b.team_id in first_solved and first_solved[b.team_id] == b.id:
            #    y = design.fts(text=lang.lang['event_queue_team'])
            #else:
            y = design.fts_no(text=lang.lang['event_queue_team'])
            balloons_html.append(design.balloon(
                color_token=balloons_text,
                color=p['color'],
                problem_comment=x,
                letter=p['letter'],
                team_comment=y,
                team_short=t['name'],
                team=t['long_name'],
                state=state_str
            ))
        balloons_html = design.table(
            header=header + " (%d)" % len (balloons),
            content=''.join (balloons_html)
        )
        return balloons_html

    balloons = db.balloons_my(event_id, user_id)
    balloons = list (map (Balloon, balloons))
    content += get_balloons_html(
        lang.lang['event_header_your_queue'],
        get_state_str_current, balloons
    )
    balloons = db.balloons_new(event_id)
    balloons = list (map (Balloon, reversed (balloons)))
    if (hall != 0):
      balloons = [b for b in balloons if config.hall_by_team_name(teams[teams_map[b.team_id]]['name']) == hall]
    content += get_balloons_html(
        lang.lang['event_header_offer'],
        get_state_str_queue, balloons
    )
    balloons = db.balloons_old_not_delivered(event_id)
    balloons = list (map (Balloon, balloons))
    content += get_balloons_html(
        lang.lang['event_header_queue'],
        get_state_str_queue, balloons
    )
    balloons = db.balloons_old_delivered(event_id)
    balloons = list (map (Balloon, balloons))
    content += get_balloons_html(
        lang.lang['event_header_delivered'],
        get_state_str_queue, balloons
    )

    db.close()
    response = make_response(render_template(
        'template.html',
        title=event['name'],
        base=config.base_url,
        content=content
    ))
    token = auth.create_token(user_id, add_random=True)
    response.set_cookie('ball_token', token)
    return response


@ball.route('/event<int:event>/standings')
def event_standings(event):
    user_id, auth_html, user_ok = check_auth(request)
    if not user_ok:
        return redirect(url_for('index'))
    event_id = int(event)
    db = DB()
    try:
        e = db.event(event_id)
    except KeyError:
        return redirect(url_for('index'))
    event = {
        'name': e[1],
        'state': e[2],
        'url': e[3]
    }
    problems_header = []
    problems = db.problems(event_id)
    for p in problems:
        problems_header.append(design.standings_problem(
            name_full=p['name'],
            name_short=p['letter']
        ))
        try:
            p['fts'] = db.fts(event_id, problem_id=p['id'])
        except KeyError:
            pass

    oks = {}
    for b in db.balloons(event_id):
        oks[(b['team_id'], b['problem_id'])] = (b['id'], b['time_local'])

    standings_header = ''.join(problems_header)
    teams = []
    content = '<table>'
    for t in sorted(db.teams(event_id), key=lambda t: t['name']):
        if not t['name'].startswith('S'):
          # Hack for NEERC-2017: 'S' is for St. Petersburg
          continue
        content += '<tr>'
        content += '<td style="font-size: large">%s</td><td>&nbsp;</td>' % t['name']
        for p in problems:
            key = (t['id'], p['id'])
            if key in oks:
                content += '<td class="balloons_balloon_color" style="background-color: %s">%s</td>' % (
                    p['color'],p['letter'])
            else:
                content += '<td><strike>%s</strike></td>' % p['letter']
        content += '<td>&nbsp;&nbsp;&nbsp;</td><td>%s</td>' % t['long_name']
        content += '<tr>'
    content += '</table>'

    db.close()
    return page(
        title=event['name'],
        content=content
    )


user_cache = {}
def check_auth(request):
    auth_html = design.auth(url=url_for('method_auth'))
    try:
        user_id = request.cookies.get('ball_user_id')
        auth_token = request.cookies.get('ball_auth_token')
    except:
        return None, auth_html, False
    if not auth.check(user_id, auth_token):
        return None, auth_html, False
    #  need to invalidate cache in action_access_*
    # if user_id in user_cache:
    #     return user_cache[user_id]
    auth_html = design.auth_ok(user=str(user_id))
    user_ok = user_id in config.allowed_users
    if not user_ok:
        db = DB()
        user_ok = db.volunteer_has_access(user_id)
        db.close(commit=True)
    user_cache[user_id] = user_id, auth_html, user_ok
    return user_cache[user_id]


@ball.route('/auth')
def method_auth():
    user_id, auth_html, user_ok= check_auth(request)
    content = design.auth_link(url=url_for('auth_vk_start'), label='VK') + \
        design.auth_link(url=url_for('auth_google_start'), label='Google')
    return render_template(
        'template.html',
        title=lang.lang['auth'],
        auth=auth_html,
        base=config.base_url,
        content=content)


@ball.route('/auth/vk/start')
def auth_vk_start():
    return redirect(auth.vk.url)


@ball.route('/auth/vk/done')
def auth_vk_done():
    try:
        code = request.args.get('code', '')
    except:
        code = 'None'
    try:
        (user_id, name, url) = auth.vk.do (code)
    except auth.AuthentificationError as error:
        error_content = 'Failed auth: ' + str(error)
        return render_template(
            'template.html',
            title='Failed auth',
            base=config.base_url,
            content=error_content)
    db = DB()
    db.volunteer_create(user_id, name, url)
    db.close(commit=True)
    auth_token = auth.create_token(user_id)
    resp = make_response(redirect(url_for('index')))
    resp.set_cookie('ball_auth_token', auth_token)
    resp.set_cookie('ball_user_id', user_id)
    return resp


@ball.route('/auth/google/start')
def auth_google_start():
    return redirect(auth.google.url)


@ball.route('/auth/google/done')
def auth_google_done():
    try:
        code = request.args.get('code', '')
    except:
        code = 'None'
    try:
        user_id, name, url = auth.google.do(code)
    except auth.AuthentificationError as error:
        error_content = 'Failed auth: ' + str(error)
        return render_template('template.html',
                               title='Failed auth',
                               base=config.base_url,
                               content=error_content)
    db = DB()
    db.volunteer_create(user_id, name, url)
    db.close(commit=True)
    auth_token = auth.create_token(user_id)
    resp = make_response(redirect(url_for('index')))
    resp.set_cookie('ball_auth_token', auth_token)
    resp.set_cookie('ball_user_id', user_id)
    return resp

class LoggerHandler (logging.StreamHandler):
    def emit (x, record):
        logging.StreamHandler.emit (x, record)

if __name__ == '__main__':
    webc = config.config['web']
    ball.debug = webc['debug']
    ball.logger.setLevel(logging.DEBUG)
    handler = LoggerHandler()
    handler.setLevel(logging.DEBUG)
    ball.logger.addHandler(handler)
    ball.run(host=webc['host'], port=webc['port'])


