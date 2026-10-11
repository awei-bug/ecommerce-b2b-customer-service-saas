from flask_shop import db, models
from flask_shop.agents import support
from flask_shop.utils.tenant_query import tenant_context


def test_agent_memory_persists_customer_preferences(api, app):
    seed = api['seed']
    with app.app_context(), tenant_context(disabled=True):
        context = support.save_memory_turn(
            tenant_id=seed['id_a'],
            session_id='memory-session',
            customer_id=None,
            user_text='预算300元，喜欢黑色L码夹克',
            reply='已记录你的筛选条件。',
            products=[{'id': 1, 'name': '黑色夹克', 'price': 299}],
            intent={'intent': 'search', 'keywords': ['夹克'], 'budget_max': 300},
        )
        loaded = support.get_memory_context(seed['id_a'], 'memory-session')
        assert loaded['turn_count'] == 1
        assert loaded['preferences']['budget_max'] == 300
        assert loaded['preferences']['size'] == 'L'
        assert loaded['preferences']['colors'] == ['黑色']
        assert loaded['last_products'][0]['name'] == '黑色夹克'
        assert models.AgentMemory.query.count() == 1
