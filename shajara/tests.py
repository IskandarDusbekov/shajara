import json
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .matching import FamilyGraph, block_key, fold, jaro_winkler, patronymic_root, run_matching, score_pair, surname_root
from .merge import MergeConflict, execute_merge, preview_merge
from .models import ActivityLog, Family, MatchCandidate, MergeRecord, Person, PersonStory, Tree

User = get_user_model()


def person(first, last="", gender="erkak", **extra):
    return Person.objects.create(first_name=first, last_name=last, gender=gender, **extra)


def family(father=None, mother=None, children=()):
    fam = Family.objects.create(father=father, mother=mother)
    for child in children:
        child.child_family = fam
        child.save(update_fields=["child_family"])
    return fam


class NormalisationTests(TestCase):
    def test_spelling_variants_fold_together(self):
        self.assertEqual(fold("Xo'jayev"), fold("Khodjayev"))
        self.assertEqual(fold("Ahmad"), fold("Axmad"))
        self.assertEqual(fold("Абдулла"), fold("Abdulla"))
        self.assertEqual(fold("G‘ofur"), fold("G'ofur"))

    def test_surname_and_patronymic_roots(self):
        self.assertEqual(surname_root("Karimov"), surname_root("Karimova"))
        self.assertEqual(patronymic_root("Ahmadovich"), "ahmad")
        self.assertEqual(patronymic_root("Ahmad o'g'li"), "ahmad")
        self.assertEqual(patronymic_root("Ахмадовна"), "ahmad")

    def test_blocking_keeps_variants_in_one_block(self):
        self.assertEqual(block_key("erkak", "Muhammad"), block_key("erkak", "Mohammed"))
        self.assertNotEqual(block_key("erkak", "Botir"), block_key("ayol", "Botir"))

    def test_jaro_winkler_bounds(self):
        self.assertEqual(jaro_winkler("botir", "botir"), 1.0)
        self.assertGreater(jaro_winkler("muhammad", "mohammed"), 0.8)
        self.assertLess(jaro_winkler("botir", "zulfiya"), 0.6)


class ScoringTests(TestCase):
    def setUp(self):
        self.owner1 = User.objects.create_user("u1", password="x")
        self.owner2 = User.objects.create_user("u2", password="x")

    def _two_trees(self, a_kwargs, b_kwargs, fathers=("Ahmad", "Ahmad")):
        a = person(**a_kwargs)
        b = person(**b_kwargs)
        fa, fb = person(fathers[0]), person(fathers[1])
        family(father=fa, children=[a])
        family(father=fb, children=[b])
        Tree.objects.create(owner=self.owner1, root_person=a, name="T1")
        Tree.objects.create(owner=self.owner2, root_person=b, name="T2")
        return a, b

    def test_strong_match_scores_high(self):
        a, b = self._two_trees(
            dict(first="Botir", last="Karimov", birth_year="1950", birth_region="Samarqand viloyati",
                 birth_district="Urgut"),
            dict(first="Botir", last="Karimov", birth_year="1952",
                 birth_region="Samarqand viloyati", birth_district="Urgut tumani"),
        )
        score, parts = score_pair(FamilyGraph(), a.id, b.id)
        by_key = {p["key"]: p for p in parts}
        self.assertEqual(by_key["place"]["detail"], "viloyat mos, tuman mos")   # "tumani" ignored
        # Unknown evidence earns nothing, so agreeing on name, years, place and
        # father lands in the "high" band without reaching "very high".
        self.assertGreaterEqual(score, 70)
        self.assertLess(score, 85)

    def test_everything_agreeing_scores_very_high(self):
        a, b = self._two_trees(
            dict(first="Botir", last="Karimov", birth_year="1950", death_year="2010",
                 birth_region="Samarqand viloyati", birth_district="Urgut", birth_village="Kamangaron"),
            dict(first="Botir", last="Karimov", birth_year="1950", death_year="2011",
                 birth_region="Samarqand viloyati", birth_district="Urgut tumani", birth_village="Kamangaron"),
        )
        for p in (a, b):
            wife, kid = person("Nodira", gender="ayol"), person("Aziz")
            family(father=p, mother=wife, children=[kid])
            p.child_family.mother = person("Zuhra", gender="ayol")
            p.child_family.save()
        score, _ = score_pair(FamilyGraph(), a.id, b.id)
        self.assertGreaterEqual(score, 90)

    def test_name_only_stays_below_threshold(self):
        a = person("Botir", "Karimov")
        b = person("Botir", "Karimov")
        Tree.objects.create(owner=self.owner1, root_person=a, name="T1")
        Tree.objects.create(owner=self.owner2, root_person=b, name="T2")
        score, _ = score_pair(FamilyGraph(), a.id, b.id)
        self.assertLess(score, 45)

    def test_contradictions_rule_out(self):
        a, b = self._two_trees(dict(first="Botir", birth_year="1900"), dict(first="Botir", birth_year="1950"))
        self.assertIsNone(score_pair(FamilyGraph(), a.id, b.id))
        c = person("Botir", gender="erkak")
        d = person("Botir", gender="ayol")
        self.assertIsNone(score_pair(FamilyGraph(), c.id, d.id))

    def test_different_father_costs_points(self):
        a, b = self._two_trees(dict(first="Botir", last="Karimov", birth_year="1950"),
                               dict(first="Botir", last="Karimov", birth_year="1950"))
        same = score_pair(FamilyGraph(), a.id, b.id)[0]
        c, d = self._two_trees(dict(first="Botir", last="Karimov", birth_year="1950"),
                               dict(first="Botir", last="Karimov", birth_year="1950"), fathers=("Ahmad", "Sobir"))
        other = score_pair(FamilyGraph(), c.id, d.id)[0]
        self.assertGreater(same, other + 20)

    def test_family_matching_as_a_family_is_corroborated_and_twins_are_not_crossed(self):
        def build(owner):
            father = person("Ahmad", "Karimov", birth_year="1940")
            husan, hasan = person("Husan", birth_year="2017"), person("Hasan", birth_year="2017")
            family(father=father, children=[husan, hasan])
            Tree.objects.create(owner=owner, root_person=father, name=owner.username)
            return father, husan, hasan

        f1, husan1, hasan1 = build(self.owner1)
        f2, husan2, hasan2 = build(self.owner2)
        run_matching()
        pairs = {c.pair_key: c for c in MatchCandidate.objects.all()}
        self.assertIn(MatchCandidate.key_for(husan1.id, husan2.id), pairs)
        self.assertIn(MatchCandidate.key_for(hasan1.id, hasan2.id), pairs)
        self.assertNotIn(MatchCandidate.key_for(husan1.id, hasan2.id), pairs)   # twin crossed over
        father_pair = pairs[MatchCandidate.key_for(f1.id, f2.id)]
        self.assertIn("relatives", {p["key"] for p in father_pair.breakdown})

    def test_run_matching_skips_connected_people_and_respects_rejections(self):
        a, b = self._two_trees(dict(first="Botir", last="Karimov", birth_year="1950"),
                               dict(first="Botir", last="Karimov", birth_year="1951"))
        run = run_matching()
        self.assertEqual(run.candidates_found, 1)
        cand = MatchCandidate.objects.get()
        cand.status = "rejected"
        cand.save()
        run_matching()
        self.assertEqual(MatchCandidate.objects.get().status, "rejected")


class MergeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("boss", password="x", is_staff=True)
        u1 = User.objects.create_user("u1", password="x")
        u2 = User.objects.create_user("u2", password="x")

        # Tree 1: Ahmad + Zuhra -> Botir, Karim
        self.ahmad1, self.zuhra1 = person("Ahmad", "Karimov"), person("Zuhra", gender="ayol")
        self.botir1, self.karim1 = person("Botir", "Karimov", birth_year="1950"), person("Karim")
        family(self.ahmad1, self.zuhra1, [self.botir1, self.karim1])
        self.t1 = Tree.objects.create(owner=u1, root_person=self.botir1, name="Birinchi")

        # Tree 2: Axmad -> Botir (occupation known), Salim; Botir married Nodira -> Aziz
        self.ahmad2 = person("Axmad", "Karimov", death_year="1990")
        self.botir2 = person("Botir", "Karimov", occupation="O'qituvchi")
        self.salim2 = person("Salim")
        family(self.ahmad2, None, [self.botir2, self.salim2])
        self.nodira2, self.aziz2 = person("Nodira", gender="ayol"), person("Aziz")
        family(self.botir2, self.nodira2, [self.aziz2])
        PersonStory.objects.create(person=self.botir2, text="Hikoya")
        self.t2 = Tree.objects.create(owner=u2, root_person=self.botir2, name="Ikkinchi")

    def test_preview_changes_nothing(self):
        before = (Person.objects.count(), Family.objects.count())
        log, merged, trees, error = preview_merge(self.botir1.id, self.botir2.id)
        self.assertIsNone(error)
        self.assertEqual(merged, 2)          # Botir, and the father through the parent family
        self.assertEqual({t["name"] for t in trees}, {"Birinchi", "Ikkinchi"})
        self.assertEqual((Person.objects.count(), Family.objects.count()), before)

    def test_merge_joins_both_graphs_without_losing_anyone(self):
        record = execute_merge(self.botir1.id, self.botir2.id, actor=self.admin)
        self.assertIsInstance(record, MergeRecord)

        self.assertFalse(Person.objects.filter(pk=self.botir2.id).exists())
        self.assertFalse(Person.objects.filter(pk=self.ahmad2.id).exists())   # same father, folded in

        botir = Person.objects.get(pk=self.botir1.id)
        self.assertEqual(botir.occupation, "O'qituvchi")                     # blank field filled
        self.assertEqual(botir.stories.count(), 1)                            # story moved
        ahmad = Person.objects.get(pk=self.ahmad1.id)
        self.assertEqual(ahmad.death_year, "1990")

        siblings = set(botir.child_family.children.values_list("first_name", flat=True))
        self.assertEqual(siblings, {"Botir", "Karim", "Salim"})               # nobody lost
        self.assertEqual(botir.child_family.mother_id, self.zuhra1.id)
        self.assertEqual(botir.spouses()[0][1].first_name, "Nodira")          # marriage moved

        # Both trees now show one connected family, and tree 2 is re-rooted.
        self.t2.refresh_from_db()
        self.assertEqual(self.t2.root_person_id, botir.id)
        from .tree import person_ids_in_tree
        self.assertIn(self.aziz2.id, person_ids_in_tree(self.t1.root_person))

    def test_gender_conflict_is_refused_atomically(self):
        zuhra2 = person("Zuhra", gender="ayol")
        before = Person.objects.count()
        with self.assertRaises(MergeConflict):
            execute_merge(self.botir1.id, zuhra2.id, actor=self.admin)
        self.assertEqual(Person.objects.count(), before)


class AdminPanelAccessTests(TestCase):
    def test_only_staff_can_open_the_panel(self):
        user = User.objects.create_user("plain", password="x")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("boshqaruv:dashboard")).status_code, 404)
        staff = User.objects.create_user("staff", password="x", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("boshqaruv:dashboard")).status_code, 200)

    def test_login_is_logged(self):
        User.objects.create_user("someone", password="parol123")
        self.client.post(reverse("login"), {"username": "someone", "password": "parol123"})
        self.assertTrue(ActivityLog.objects.filter(action="login", user__username="someone").exists())


class AdminMergeFlowTests(MergeTests):
    """The whole review path through the panel, on the MergeTests family."""

    def test_panel_merge_needs_confirmation_then_merges_and_logs(self):
        run_matching()
        cand = MatchCandidate.objects.get(pair_key=MatchCandidate.key_for(self.botir1.id, self.botir2.id))
        self.client.force_login(self.admin)
        url = reverse("boshqaruv:match_detail", args=[cand.pk])

        page = self.client.get(url + "?keep=a")
        self.assertContains(page, "Birlashtirish rejasi")
        self.assertContains(page, "bitta oila grafiga ulanadi")       # two different owners

        # Without ticking "I understand" nothing happens.
        self.client.post(url, {"action": "merge", "keep": "a"})
        self.assertTrue(Person.objects.filter(pk=self.botir2.id).exists())

        response = self.client.post(url, {"action": "merge", "keep": "a", "understood": "1"})
        record = MergeRecord.objects.get()
        self.assertRedirects(response, reverse("boshqaruv:merge_detail", args=[record.pk]))
        self.assertFalse(Person.objects.filter(pk=self.botir2.id).exists())
        cand.refresh_from_db()
        self.assertEqual(cand.status, "merged")
        self.assertTrue(ActivityLog.objects.filter(action="admin_merge", user=self.admin).exists())

        # Both owners' maps still render the joined family.
        for tree in (self.t1, self.t2):
            self.client.force_login(tree.owner)
            self.assertEqual(self.client.get(reverse("index", args=[tree.url_key])).status_code, 200)

    def test_reject_is_remembered(self):
        run_matching()
        cand = MatchCandidate.objects.get(pair_key=MatchCandidate.key_for(self.botir1.id, self.botir2.id))
        self.client.force_login(self.admin)
        self.client.post(reverse("boshqaruv:match_detail", args=[cand.pk]), {"action": "reject", "note": "boshqa odam"})
        run_matching()
        cand.refresh_from_db()
        self.assertEqual((cand.status, cand.note), ("rejected", "boshqa odam"))


class MapAndActivityTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("egasi", password="x")
        self.guest = User.objects.create_user("mehmon", password="x")
        self.root = person("Botir", "Karimov")
        self.tree = Tree.objects.create(owner=self.owner, root_person=self.root, name="Oila", visibility="public")

    def test_one_map_page_owner_gets_add_shortcuts_guest_does_not(self):
        self.client.force_login(self.owner)
        page = self.client.get(reverse("index", args=[self.tree.url_key]))
        self.assertContains(page, "Qarindosh qo'shish")
        self.client.force_login(self.guest)
        page = self.client.get(reverse("index", args=[self.tree.url_key]))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "Qarindosh qo'shish")
        old = self.client.get(f"/shajara/{self.tree.url_key}/korish/")
        self.assertRedirects(old, reverse("index", args=[self.tree.url_key]), status_code=301)

    def test_identity_fields_are_saved_and_actions_logged(self):
        self.client.force_login(self.owner)
        url = reverse("add_relative", args=[self.tree.url_key]) + f"?anchor={self.root.id}&relation=ota"
        self.client.post(url, {
            "first_name": "Ahmad", "last_name": "Karimov", "patronymic": "Sobirovich",
            "birth_year": "1930", "birth_region": "Samarqand viloyati", "birth_district": "Urgut",
            "birth_village": "Kamangaron", "anchor": self.root.id, "relation": "ota",
        })
        father = Person.objects.get(first_name="Ahmad")
        self.assertEqual((father.patronymic, father.birth_region, father.birth_village),
                         ("Sobirovich", "Samarqand viloyati", "Kamangaron"))
        self.assertEqual(father.birth_place, "Kamangaron, Urgut, Samarqand viloyati")
        entry = ActivityLog.objects.get(action="person_add")
        self.assertEqual((entry.user, entry.tree, entry.person), (self.owner, self.tree, father))

    def test_staff_looking_into_a_private_tree_is_logged(self):
        self.tree.visibility = "private"
        self.tree.save()
        staff = User.objects.create_user("nazoratchi", password="x", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("index", args=[self.tree.url_key])).status_code, 200)
        self.assertTrue(ActivityLog.objects.filter(action="admin_view_private", user=staff, tree=self.tree).exists())
        self.client.force_login(self.guest)
        self.assertEqual(self.client.get(reverse("index", args=[self.tree.url_key])).status_code, 403)


class RegionTextTests(TestCase):
    def test_regions_are_recognised_in_free_text(self):
        from .regions import region_from_text
        self.assertEqual(region_from_text("Samarqand, Urgut tumani"), "Samarqand viloyati")
        self.assertEqual(region_from_text("Nukus"), "Qoraqalpog'iston Respublikasi")
        self.assertEqual(region_from_text("Qarshi shahri"), "Qashqadaryo viloyati")
        self.assertEqual(region_from_text("Toshkent"), "Toshkent shahri")
        self.assertEqual(region_from_text("Moskva"), "Boshqa")
        self.assertEqual(region_from_text("Shirinoy"), "")


class UnifiedTreeTests(MergeTests):
    """The virtual merge on the MergeTests family: two trees, one Botir."""

    def test_unified_graph_merges_virtually_and_touches_nothing(self):
        from .unified import UnifiedGraph
        run_matching()
        before = (Person.objects.count(), Family.objects.count())
        u = UnifiedGraph(min_score=45)
        self.assertEqual((Person.objects.count(), Family.objects.count()), before)   # nothing written

        botir = u.of[self.botir1.id]
        self.assertEqual(botir, u.of[self.botir2.id])                                # same individual
        self.assertEqual(u.of[self.ahmad1.id], u.of[self.ahmad2.id])                 # father follows by structure
        self.assertEqual(u.conflicts, [])
        network = u.family_networks()[0]
        self.assertEqual(len(network["trees"]), 2)
        self.assertEqual(network["duplicates"], 2)
        board = u.board(network["key"])
        names = {p.first_name for p in board["people"]}
        self.assertTrue({"Botir", "Karim", "Salim", "Nodira", "Aziz", "Zuhra"} <= names)

    def test_rejected_match_is_never_merged_virtually(self):
        from .unified import UnifiedGraph
        run_matching()
        MatchCandidate.objects.update(status="rejected")
        u = UnifiedGraph(min_score=45)
        self.assertNotEqual(u.of[self.botir1.id], u.of[self.botir2.id])

    def test_map_and_unified_pages_are_staff_only(self):
        from .unified import UnifiedGraph
        run_matching()
        self.botir1.birth_region = "Samarqand viloyati"
        self.botir1.save()
        key = UnifiedGraph(70).family_networks()[0]["key"]
        urls = [reverse("boshqaruv:map"), reverse("boshqaruv:unified"),
                reverse("boshqaruv:unified_board", args=[key]),
                reverse("boshqaruv:unified_person", args=[self.botir1.id])]
        self.client.force_login(self.t1.owner)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.client.force_login(self.admin)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        page = self.client.get(reverse("boshqaruv:map"))
        samarqand = page.context["map_data"]["rows"]["Samarqand viloyati"]
        self.assertEqual((samarqand["people"], samarqand["trees"]), (1, 1))   # Botir and the tree rooted in him
        live = self.client.get(reverse("boshqaruv:map_live")).json()
        self.assertEqual(live["total"], 2)                                      # the owner tried, the admin is here
        self.client.force_login(self.t1.owner)
        self.assertEqual(self.client.get(reverse("boshqaruv:map_live")).status_code, 404)

    def test_user_region_is_saved_from_registration(self):
        self.client.post(reverse("register"), {
            "first_name": "Ali", "username": "ali_uz", "region": "Andijon viloyati",
            "password1": "parol123", "password2": "parol123",
        })
        from .models import UserProfile
        self.assertEqual(UserProfile.objects.get(user__username="ali_uz").region, "Andijon viloyati")


class TreeLayoutTests(TestCase):
    """Saving the card arrangement from the map."""

    def setUp(self):
        from .models import Family, Person, Tree
        self.owner = User.objects.create_user("layout_owner", password="pw-12345678")
        self.other = User.objects.create_user("layout_other", password="pw-12345678")
        self.father = Person.objects.create(first_name="Ota", last_name="X", gender="erkak")
        fam = Family.objects.create(father=self.father)
        self.child = Person.objects.create(first_name="Bola", last_name="X", gender="erkak", child_family=fam)
        self.stranger = Person.objects.create(first_name="Begona", last_name="Y", gender="erkak")
        self.tree = Tree.objects.create(owner=self.owner, root_person=self.child, name="T")
        self.url = reverse("tree_layout", args=[self.tree.url_key])

    def post(self, payload):
        return self.client.post(self.url, data=json.dumps(payload), content_type="application/json")

    def test_owner_saves_only_people_of_the_tree(self):
        self.client.force_login(self.owner)
        r = self.post({"positions": {
            str(self.father.id): [10, 20.26], str(self.child.id): [30, 90],
            str(self.stranger.id): [1, 1], "abc": [1, 1], str(self.father.id) + "0": [1, 1],
        }})
        self.assertEqual(r.status_code, 200)
        self.tree.refresh_from_db()
        self.assertEqual(self.tree.layout, {str(self.father.id): [10, 20.3], str(self.child.id): [30, 90]})
        page = self.client.get(reverse("index", args=[self.tree.url_key]))
        self.assertContains(page, 'id="layout-data"')
        self.assertContains(page, "data-layout-url")

    def test_bad_values_are_dropped_and_empty_clears(self):
        self.client.force_login(self.owner)
        self.post({"positions": {str(self.child.id): ["1", 2], str(self.father.id): [True, 2]}})
        self.tree.refresh_from_db()
        self.assertEqual(self.tree.layout, {})
        self.assertEqual(self.post({"positions": []}).status_code, 400)
        self.assertEqual(self.client.post(self.url, data="nope", content_type="application/json").status_code, 400)

    def test_only_the_owner_may_save(self):
        self.client.force_login(self.other)
        self.assertEqual(self.post({"positions": {}}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.post({"positions": {}}).status_code, 302)
        self.assertEqual(self.client.get(self.url).status_code, 302)


class SharedTreeTests(TestCase):
    """One person starts a tree, relatives join by link and build it together."""

    def setUp(self):
        from .models import Family, Person, Tree
        self.owner = User.objects.create_user("sh_owner", password="pw-12345678")
        self.relative = User.objects.create_user("sh_relative", password="pw-12345678")
        self.stranger = User.objects.create_user("sh_stranger", password="pw-12345678")
        self.grandpa = Person.objects.create(first_name="Karim", last_name="Aliyev", gender="erkak", added_by=self.owner)
        fam = Family.objects.create(father=self.grandpa)
        self.me = Person.objects.create(first_name="Siddiq", last_name="Aliyev", gender="erkak",
                                        child_family=fam, added_by=self.owner)
        self.tree = Tree.objects.create(owner=self.owner, root_person=self.me, name="Aliyevlar")
        self.key = self.tree.url_key

    def make_invite(self, role="muharrir"):
        self.client.force_login(self.owner)
        r = self.client.post(reverse("invite_create", args=[self.key]), {"role": role, "ttl": "7"})
        self.assertEqual(r.status_code, 302)
        self.client.logout()
        from .models import TreeInvite
        return TreeInvite.objects.filter(tree=self.tree).first()

    def test_private_tree_is_closed_until_joining(self):
        self.client.force_login(self.relative)
        self.assertEqual(self.client.get(reverse("index", args=[self.key])).status_code, 403)
        self.assertEqual(self.client.get(reverse("tree_members", args=[self.key])).status_code, 403)

    def test_invite_flow_signed_out_then_join(self):
        invite = self.make_invite("muharrir")
        url = reverse("invite_accept", args=[invite.token])
        page = self.client.get(url)
        self.assertContains(page, "Aliyevlar")
        self.assertContains(page, f"next={url}")
        self.client.force_login(self.relative)
        self.assertContains(self.client.get(url), "Qo'shilish")
        r = self.client.post(url)
        self.assertRedirects(r, reverse("index", args=[self.key]))
        from .models import TreeInvite, TreeMember
        member = TreeMember.objects.get(tree=self.tree, user=self.relative)
        self.assertEqual(member.role, "muharrir")
        self.assertEqual(TreeInvite.objects.get(pk=invite.pk).uses, 1)
        # joining twice changes nothing
        self.client.post(url)
        self.assertEqual(TreeMember.objects.filter(tree=self.tree).count(), 1)
        # the tree now shows up on the start page
        self.assertContains(self.client.get(reverse("my_trees")), "Menga ulashilganlar")

    def test_editor_builds_but_cannot_manage(self):
        from .models import Person, TreeMember
        TreeMember.objects.create(tree=self.tree, user=self.relative, role="muharrir")
        self.client.force_login(self.relative)
        page = self.client.get(reverse("index", args=[self.key]))
        self.assertContains(page, "data-add-url")
        r = self.client.post(
            reverse("add_relative", args=[self.key]) + f"?anchor={self.me.id}&relation=farzand",
            {"first_name": "Nevara", "last_name": "Aliyev", "gender": "erkak"},
        )
        self.assertEqual(r.status_code, 302)
        kid = Person.objects.get(first_name="Nevara")
        self.assertEqual(kid.added_by, self.relative)
        # may take back what they added, not what the owner added
        self.assertEqual(self.client.post(reverse("person_delete", args=[self.key, self.grandpa.id])).status_code, 403)
        self.assertEqual(self.client.post(reverse("person_delete", args=[self.key, kid.id])).status_code, 302)
        # owner-only pages
        self.assertEqual(self.client.get(reverse("tree_settings", args=[self.key])).status_code, 403)
        self.assertEqual(self.client.get(reverse("tree_export", args=[self.key])).status_code, 403)
        self.assertEqual(self.client.post(reverse("invite_create", args=[self.key]), {"role": "muharrir", "ttl": "7"}).status_code, 403)

    def test_viewer_only_looks(self):
        from .models import TreeMember
        TreeMember.objects.create(tree=self.tree, user=self.relative, role="kuzatuvchi")
        self.client.force_login(self.relative)
        page = self.client.get(reverse("index", args=[self.key]))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "data-add-url")
        r = self.client.get(reverse("add_relative", args=[self.key]) + f"?anchor={self.me.id}&relation=farzand")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.get(reverse("person_edit", args=[self.key, self.me.id])).status_code, 403)

    def test_owner_changes_role_removes_and_member_leaves(self):
        from .models import TreeMember
        m = TreeMember.objects.create(tree=self.tree, user=self.relative, role="muharrir")
        other = TreeMember.objects.create(tree=self.tree, user=self.stranger, role="kuzatuvchi")
        update = reverse("member_update", args=[self.key, m.pk])

        self.client.force_login(self.stranger)       # a member can't manage others
        self.assertEqual(self.client.post(update, {"action": "remove"}).status_code, 403)

        self.client.force_login(self.owner)
        self.client.post(update, {"action": "role", "role": "kuzatuvchi"})
        m.refresh_from_db()
        self.assertEqual(m.role, "kuzatuvchi")
        self.client.post(update, {"action": "remove"})
        self.assertFalse(TreeMember.objects.filter(pk=m.pk).exists())

        self.client.force_login(self.stranger)
        r = self.client.post(reverse("member_update", args=[self.key, other.pk]), {"action": "leave"})
        self.assertRedirects(r, reverse("my_trees"))
        self.assertFalse(TreeMember.objects.filter(pk=other.pk).exists())

    def test_revoked_or_expired_invite_is_dead(self):
        from datetime import timedelta
        from django.utils import timezone
        invite = self.make_invite()
        invite.revoked = True
        invite.save()
        self.client.force_login(self.relative)
        url = reverse("invite_accept", args=[invite.token])
        self.assertEqual(self.client.get(url).status_code, 410)
        self.assertEqual(self.client.post(url).status_code, 410)
        invite.revoked = False
        invite.expires_at = timezone.now() - timedelta(minutes=1)
        invite.save()
        self.assertEqual(self.client.post(url).status_code, 410)
        from .models import TreeMember
        self.assertFalse(TreeMember.objects.filter(tree=self.tree).exists())

    def test_register_with_role_returns_to_invite(self):
        invite = self.make_invite("kuzatuvchi")
        url = reverse("invite_accept", args=[invite.token])
        r = self.client.post(reverse("register"), {
            "first_name": "Yangi", "username": "yangi_talaba", "role": "talaba",
            "password1": "pw-12345678", "password2": "pw-12345678", "next": url,
        })
        self.assertRedirects(r, url)
        self.assertEqual(User.objects.get(username="yangi_talaba").profile.role, "talaba")
        # an outside address is ignored
        self.client.logout()
        r = self.client.post(reverse("register"), {
            "first_name": "Boshqa", "username": "boshqa_user",
            "password1": "pw-12345678", "password2": "pw-12345678", "next": "https://evil.example/",
        })
        self.assertRedirects(r, reverse("my_trees"))


class LearningTreeTests(TestCase):
    """Learning trees: kind and subject, the library, and the self-test."""

    def setUp(self):
        from .models import Family, Person, Tree
        self.teacher = User.objects.create_user("ustoz", password="pw-12345678")
        self.student = User.objects.create_user("oquvchi", password="pw-12345678")
        temur = Person.objects.create(first_name="Amir", last_name="Temur", gender="erkak", birth_year="1336",
                                      occupation="Hukmdor")
        wife = Person.objects.create(first_name="Saroymulk", last_name="xonim", gender="ayol")
        fam = Family.objects.create(father=temur, mother=wife)
        shohruh = Person.objects.create(first_name="Shohruh", gender="erkak", birth_year="1377",
                                        occupation="Hukmdor", child_family=fam)
        Person.objects.create(first_name="Mironshoh", gender="erkak", birth_year="1366", child_family=fam)
        fam2 = Family.objects.create(father=shohruh)
        Person.objects.create(first_name="Ulug'bek", gender="erkak", birth_year="1394",
                              occupation="Astronom", child_family=fam2)
        self.root = temur
        self.tree = Tree.objects.create(owner=self.teacher, root_person=temur, name="Temuriylar",
                                        kind="talimiy", subject="Tarix", visibility="public")

    def test_create_learning_tree(self):
        from .models import Tree
        self.client.force_login(self.teacher)
        r = self.client.post(reverse("tree_create"), {
            "kind": "talimiy", "tree_name": "Shayboniylar", "subject": "O'zbekiston tarixi", "era": "XVI asr",
            "description": "", "visibility": "private", "first_name": "Muhammad", "last_name": "Shayboniy",
            "gender": "erkak",
        })
        tree = Tree.objects.get(name="Shayboniylar")
        self.assertRedirects(r, reverse("index", args=[tree.url_key]))
        self.assertEqual((tree.kind, tree.subject, tree.era), ("talimiy", "O'zbekiston tarixi", "XVI asr"))

    def test_library_tabs_and_search(self):
        self.client.force_login(self.student)
        page = self.client.get(reverse("public_trees"))
        self.assertContains(page, "Temuriylar")
        self.assertNotContains(self.client.get(reverse("public_trees") + "?tur=oilaviy"), "Temuriylar")
        self.assertContains(self.client.get(reverse("public_trees") + "?q=Amir"), "Temuriylar")
        self.assertNotContains(self.client.get(reverse("public_trees") + "?q=Bobur"), "pf-tree is-talimiy")

    def test_quiz_questions_come_from_the_tree(self):
        import random
        from .quiz import build_quiz
        questions = build_quiz(self.root, random.Random(4))
        self.assertGreaterEqual(len(questions), 6)
        for q in questions:
            self.assertTrue(2 <= len(q["options"]) <= 4)
            self.assertEqual(len(set(q["options"])), len(q["options"]))
            self.assertIn(q["answer"], range(len(q["options"])))
        by_text = {q["text"]: q for q in questions}
        father_q = by_text.get("Ulug'bekning otasi kim?")
        if father_q:
            self.assertEqual(father_q["options"][father_q["answer"]], "Shohruh")

    def test_quiz_grades_on_the_server_and_records_the_score(self):
        from .models import QuizAttempt
        self.client.force_login(self.student)
        page = self.client.get(reverse("tree_quiz", args=[self.tree.url_key]))
        self.assertEqual(page.status_code, 200)
        state = self.client.session[f"quiz:{self.tree.pk}"]
        self.assertNotIn('"answer"', page.content.decode())
        answer_url = reverse("tree_quiz_answer", args=[self.tree.url_key])
        total = len(state["answers"])
        for i, right in enumerate(state["answers"]):
            choice = right if i % 2 == 0 else (right + 1) % 2
            r = self.client.post(answer_url, data=json.dumps({"q": i, "choice": choice}), content_type="application/json")
            self.assertEqual(r.json()["correct"], right)
        # changing a locked-in answer doesn't help
        r = self.client.post(answer_url, data=json.dumps({"q": 1, "choice": state["answers"][1]}),
                             content_type="application/json")
        attempt = QuizAttempt.objects.get(tree=self.tree, user=self.student)
        self.assertEqual(attempt.total, total)
        self.assertEqual(attempt.score, (total + 1) // 2)
        self.assertEqual(r.json()["score"], attempt.score)

        # the teacher sees it once the student is in the class
        from .models import TreeMember
        TreeMember.objects.create(tree=self.tree, user=self.student, role="kuzatuvchi")
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse("tree_members", args=[self.tree.url_key])), "Test:")

    def test_private_learning_tree_quiz_needs_access(self):
        self.tree.visibility = "private"
        self.tree.save()
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("tree_quiz", args=[self.tree.url_key])).status_code, 403)
        r = self.client.post(reverse("tree_quiz_answer", args=[self.tree.url_key]),
                             data=json.dumps({"q": 0, "choice": 0}), content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_start_page_hint_follows_role(self):
        from .models import UserProfile
        UserProfile.objects.create(user=self.teacher, role="oqituvchi")
        self.client.force_login(self.teacher)
        self.assertContains(self.client.get(reverse("my_trees")), "O'qituvchilar uchun")
        self.client.logout()
        self.assertContains(self.client.get(reverse("landing")), "Oila uchun ham, sinf xonasi uchun ham")


class PersonYearAndPlaceTests(TestCase):
    """Typing years and birth places on the person form."""

    def setUp(self):
        from .models import Person, Tree
        self.owner = User.objects.create_user("yil_owner", password="pw-12345678")
        self.me = Person.objects.create(first_name="Aziz", gender="erkak")
        self.tree = Tree.objects.create(owner=self.owner, root_person=self.me, name="Yillar")
        self.client.force_login(self.owner)
        self.url = reverse("person_edit", args=[self.tree.url_key, self.me.id])

    def post(self, **extra):
        data = {"first_name": "Aziz", "gender": "erkak"}
        data.update(extra)
        return self.client.post(self.url, data)

    def test_normalise_year(self):
        from django import forms as djforms
        from .forms import normalise_year
        self.assertEqual(normalise_year("1956"), "1956")
        self.assertEqual(normalise_year("1956", approx=True), "~1956")
        self.assertEqual(normalise_year("taxminan 1956"), "~1956")
        self.assertEqual(normalise_year(""), "")
        for bad in ("abc", "3000", "19x6"):
            with self.assertRaises(djforms.ValidationError):
                normalise_year(bad)

    def test_approximate_year_and_place_are_saved(self):
        r = self.post(birth_year="1956", birth_year_approx="on", birth_region="Samarqand viloyati",
                      birth_district="Urgut", birth_village="")
        self.assertEqual(r.status_code, 302)
        self.me.refresh_from_db()
        self.assertEqual((self.me.birth_year, self.me.birth_region, self.me.birth_district),
                         ("~1956", "Samarqand viloyati", "Urgut"))
        page = self.client.get(self.url)
        self.assertContains(page, 'value="1956"')
        self.assertContains(page, 'name="birth_year_approx" checked')

    def test_place_unknown_is_fine(self):
        self.assertEqual(self.post(birth_year="", birth_region="").status_code, 302)
        self.me.refresh_from_db()
        self.assertEqual((self.me.birth_year, self.me.birth_region), ("", ""))

    def test_date_sets_year_and_bad_orders_are_refused(self):
        self.post(birth_date="1990-05-04", birth_year="1980")
        self.me.refresh_from_db()
        self.assertEqual(self.me.birth_year, "1990")
        r = self.post(birth_year="1990", death_year="1980")
        self.assertContains(r, "tug'ilgan yildan oldin")
        r = self.post(birth_year="2999")
        self.assertContains(r, "kelajakda")


class RegisterEmailOtpTests(TestCase):
    def test_email_on_signup_goes_to_code_page_then_back(self):
        from django.core import mail
        from .models import EmailOTP, TreeInvite
        r = self.client.post(reverse("register"), {
            "first_name": "Aziz", "username": "aziz_karimov", "email": "aziz@example.com",
            "password1": "pw-12345678", "password2": "pw-12345678", "next": "/shajaralarim/?tur=talimiy",
        })
        self.assertRedirects(r, reverse("email_verify"))
        self.assertEqual(len(mail.outbox), 1)
        otp = EmailOTP.objects.get(user__username="aziz_karimov", purpose="verify")
        self.assertIn(otp.code, mail.outbox[0].body)
        page = self.client.get(reverse("email_verify"))
        self.assertContains(page, "Keyinroq tasdiqlayman")
        r = self.client.post(reverse("email_verify"), {"code": otp.code})
        self.assertRedirects(r, "/shajaralarim/?tur=talimiy")
        self.assertTrue(User.objects.get(username="aziz_karimov").profile.email_verified)

    def test_signup_page_shows_username_example(self):
        self.assertContains(self.client.get(reverse("register")), "aziz_karimov")


class BookAndPictureExportTests(TestCase):
    """PDF book, picture check codes, the public check page and share previews."""

    def setUp(self):
        import tempfile
        from django.test import override_settings
        from .models import Family, Person, Tree, TreeMember
        self._media = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._media.name)
        self._override.enable()
        self.owner = User.objects.create_user("kitob_owner", password="pw-12345678", first_name="Aziz")
        self.viewer = User.objects.create_user("kitob_viewer", password="pw-12345678")
        self.stranger = User.objects.create_user("kitob_stranger", password="pw-12345678")
        grandpa = Person.objects.create(first_name="Karim", gender="erkak", birth_year="~1920", occupation="Dehqon",
                                        birth_region="Samarqand viloyati", birth_district="Urgut", bio="Qishloqda tug'ilgan.")
        grandma = Person.objects.create(first_name="Ro'zigul", gender="ayol")
        fam = Family.objects.create(father=grandpa, mother=grandma)
        dad = Person.objects.create(first_name="Siddiq", gender="erkak", birth_year="1950", death_year="2010", child_family=fam)
        Person.objects.create(first_name="Sherqul", gender="erkak", child_family=fam)
        fam2 = Family.objects.create(father=dad)
        self.me = Person.objects.create(first_name="Aziz", gender="erkak", birth_year="1985", child_family=fam2)
        self.tree = Tree.objects.create(owner=self.owner, root_person=self.me, name="Karimovlar")
        TreeMember.objects.create(tree=self.tree, user=self.viewer, role="kuzatuvchi")
        self.key = self.tree.url_key

    def tearDown(self):
        self._override.disable()
        self._media.cleanup()

    def png_bytes(self, size=(1200, 630)):
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", size, "#fbf7ec").save(buf, format="PNG")
        return buf.getvalue()

    def test_lineage_numbers(self):
        from .book import Lineage
        lin = Lineage(self.me)
        numbers = {lin.people[pid].first_name: num for pid, num, _ in lin.register}
        self.assertEqual(numbers["Karim"], "1")
        self.assertEqual(numbers["Siddiq"], "1.1")
        self.assertEqual(numbers["Sherqul"], "1.2")
        self.assertEqual(numbers["Aziz"], "1.1.1")
        self.assertNotIn("Ro'zigul", numbers)       # she appears beside her husband
        self.assertIn("1 ning turmush", lin.label_for(next(p for p in lin.people if lin.people[p].first_name == "Ro'zigul")))

    def test_pdf_book_for_members_with_check_record(self):
        from .models import ExportRecord
        self.client.force_login(self.viewer)
        r = self.client.get(reverse("tree_pdf", args=[self.key]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertIn("karimovlar-kitob.pdf", r["Content-Disposition"])
        record = ExportRecord.objects.get(tree=self.tree, kind="pdf")
        self.assertEqual((record.people_count, record.generations, record.created_by), (5, 3, self.viewer))

        from io import BytesIO
        from pypdf import PdfReader
        text = "".join(page.extract_text() for page in PdfReader(BytesIO(r.content)).pages)
        for expected in ("Karimovlar", "Mundarija", "Nasl ro", "Siddiq", "Dehqon", record.pretty_code,
                         "oilasi", "Farzandlari", "Keyingi avlodda"):
            self.assertIn(expected, text)

        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(reverse("tree_pdf", args=[self.key])).status_code, 403)

    def test_public_check_page(self):
        from .models import ExportRecord
        record = ExportRecord.objects.create(tree=self.tree, tree_name="Karimovlar", kind="png", created_by=self.owner,
                                             people_count=5, generations=3)
        self.client.logout()
        page = self.client.get(reverse("verify_export", args=[record.code]))
        self.assertContains(page, "Hujjat haqiqiy")
        self.assertContains(page, record.pretty_code)
        self.assertContains(self.client.get(reverse("verify_export", args=[record.pretty_code])), "Hujjat haqiqiy")
        self.assertEqual(self.client.get(reverse("verify_export", args=["NOPE000000"])).status_code, 404)

    def test_picture_record_gives_code_and_qr(self):
        self.client.force_login(self.viewer)
        url = reverse("picture_record", args=[self.key])
        r = self.client.post(url, data=json.dumps({"kind": "png"}), content_type="application/json")
        data = r.json()
        self.assertTrue(data["code"].startswith("SH-"))
        self.assertIn("<svg", data["qr_svg"])
        self.assertEqual(data["people"], 5)
        self.assertEqual(self.client.post(url, data=json.dumps({"kind": "gif"}), content_type="application/json").status_code, 400)
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.post(url, data=json.dumps({"kind": "png"}), content_type="application/json").status_code, 403)

    def test_share_preview_upload_and_invite_link_preview(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import TreeInvite
        upload = reverse("preview_upload", args=[self.key])

        self.client.force_login(self.viewer)        # viewers can't replace it
        r = self.client.post(upload, {"image": SimpleUploadedFile("p.png", self.png_bytes(), "image/png")})
        self.assertEqual(r.status_code, 403)

        self.client.force_login(self.owner)
        r = self.client.post(upload, {"image": SimpleUploadedFile("p.png", b"not an image", "image/png")})
        self.assertEqual(r.status_code, 400)
        r = self.client.post(upload, {"image": SimpleUploadedFile("p.png", self.png_bytes(), "image/png")})
        self.assertEqual(r.status_code, 200)
        self.tree.refresh_from_db()
        self.assertTrue(self.tree.preview_image)

        invite = TreeInvite.objects.create(tree=self.tree, created_by=self.owner)
        self.client.logout()
        page = self.client.get(reverse("invite_accept", args=[invite.token]))
        self.assertContains(page, 'property="og:image"')
        self.assertContains(page, "5 shaxs")
        img = self.client.get(reverse("invite_preview", args=[invite.token]))
        self.assertEqual(img.status_code, 200)
        self.assertEqual(img["Content-Type"], "image/png")
        img.close()
        invite.revoked = True
        invite.save()
        self.assertEqual(self.client.get(reverse("invite_preview", args=[invite.token])).status_code, 404)

    def test_person_form_has_searchable_place_pickers(self):
        self.client.force_login(self.owner)
        page = self.client.get(reverse("person_edit", args=[self.key, self.me.id]))
        self.assertContains(page, 'data-combo-source="birth_region"')
        self.assertContains(page, "uz-regions.js")


class HistoricalMapTests(TestCase):
    """Uploading a map, pinning places, drawing routes and who may do what."""

    def setUp(self):
        import tempfile
        from django.test import override_settings
        self._media = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._media.name)
        self._override.enable()
        self.owner = User.objects.create_user("xarita_owner", password="pw-12345678")
        self.other = User.objects.create_user("xarita_other", password="pw-12345678")

    def tearDown(self):
        self._override.disable()
        self._media.cleanup()

    def image(self, size=(800, 600), fmt="JPEG", name="old.jpg"):
        from io import BytesIO
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", size, "#e9dcbc").save(buf, format=fmt)
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")

    def make_map(self, visibility="private"):
        self.client.force_login(self.owner)
        r = self.client.post(reverse("map_create"), {
            "title": "Temur yurishlari", "era": "XIV asr", "description": "", "sources": "", "visibility": visibility,
            "tree": "", "image": self.image(),
        })
        from .models import HistoricalMap
        hmap = HistoricalMap.objects.get(title="Temur yurishlari")
        self.assertRedirects(r, reverse("map_detail", args=[hmap.url_key]))
        self.assertEqual((hmap.image_width, hmap.image_height), (800, 600))
        return hmap

    def api(self, name, hmap, body):
        return self.client.post(reverse(name, args=[hmap.url_key]), data=json.dumps(body), content_type="application/json")

    def test_upload_rejects_non_images(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.owner)
        r = self.client.post(reverse("map_create"), {
            "title": "X", "visibility": "private", "image": SimpleUploadedFile("x.jpg", b"not an image"),
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Formada xato")

    def test_places_routes_and_timeline_data(self):
        hmap = self.make_map()
        r = self.api("map_place_save", hmap, {"name": "Samarqand", "kind": "poytaxt", "x": 0.5, "y": 0.4, "year": 1370})
        samarqand = r.json()["place"]
        r = self.api("map_place_save", hmap, {"name": "Marakanda", "kind": "shahar", "x": 0.51, "y": 0.41, "year": -329})
        self.assertEqual(r.json()["place"]["year"], -329)
        dehli = self.api("map_place_save", hmap, {"name": "Dehli", "kind": "jang", "x": 0.8, "y": 0.8, "year": 1398}).json()["place"]

        bad = [
            {"name": "", "kind": "shahar", "x": 0.1, "y": 0.1},
            {"name": "A", "kind": "qasr", "x": 0.1, "y": 0.1},
            {"name": "A", "kind": "shahar", "x": 1.4, "y": 0.1},
            {"name": "A", "kind": "shahar", "x": 0.1, "y": 0.1, "year": "bir ming"},
            {"name": "A", "kind": "shahar", "x": 0.1, "y": 0.1, "year": 1400, "year_end": 1300},
        ]
        for body in bad:
            self.assertEqual(self.api("map_place_save", hmap, body).status_code, 400, body)

        r = self.api("map_route_save", hmap, {"name": "Hindiston yurishi", "kind": "harbiy", "color": "#b3261e",
                                              "stops": [{"place": samarqand["id"], "year": 1398}, {"place": dehli["id"]}]})
        route = r.json()["route"]
        self.assertEqual(route["stops"], [{"place": samarqand["id"], "year": 1398}, {"place": dehli["id"], "year": None}])
        self.assertEqual(self.api("map_route_save", hmap, {"name": "X", "color": "red"}).status_code, 400)
        self.assertEqual(self.api("map_route_save", hmap, {"name": "X", "stops": [{"place": 999999}]}).status_code, 400)

        # moving a place keeps its other fields
        self.api("map_place_save", hmap, {"id": dehli["id"], "x": 0.7, "y": 0.75})
        page = self.client.get(reverse("map_detail", args=[hmap.url_key]))
        self.assertContains(page, "Hindiston yurishi")
        data = page.context["map_data"]
        moved = next(p for p in data["places"] if p["id"] == dehli["id"])
        self.assertEqual((moved["x"], moved["year"], moved["name"]), (0.7, 1398, "Dehli"))

        # deleting a place takes it out of routes
        r = self.api("map_place_save", hmap, {"id": dehli["id"], "delete": True})
        self.assertEqual(r.json()["routes"][0]["stops"], [{"place": samarqand["id"], "year": 1398}])

    def test_private_map_is_closed_and_only_owner_edits(self):
        hmap = self.make_map("private")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("map_detail", args=[hmap.url_key])).status_code, 404)
        self.assertEqual(self.client.get(reverse("map_image", args=[hmap.url_key])).status_code, 404)
        hmap.visibility = "public"
        hmap.save()
        page = self.client.get(reverse("map_detail", args=[hmap.url_key]))
        self.assertEqual(page.status_code, 200)
        self.assertFalse(page.context["can_edit"])
        img = self.client.get(reverse("map_image", args=[hmap.url_key]))
        self.assertEqual(img.status_code, 200)
        img.close()
        self.assertEqual(self.api("map_place_save", hmap, {"name": "A", "kind": "shahar", "x": 0.1, "y": 0.1}).status_code, 403)
        self.assertEqual(self.client.get(reverse("map_settings", args=[hmap.url_key])).status_code, 403)
        self.assertContains(self.client.get(reverse("maps")), "Temur yurishlari")

    def test_sample_maps_command(self):
        from django.core.management import call_command
        from io import StringIO
        from .models import HistoricalMap, MapRoute
        call_command("seed_maps", stdout=StringIO())
        samples = HistoricalMap.objects.filter(is_sample=True)
        self.assertEqual(samples.count(), 3)
        temur = samples.get(title__startswith="Amir Temur")
        self.assertGreaterEqual(temur.places.count(), 15)
        for route in MapRoute.objects.filter(map__in=samples):
            ids = set(route.map.places.values_list("id", flat=True))
            self.assertTrue(all(s["place"] in ids for s in route.stops))
            self.assertGreaterEqual(len(route.stops), 2)
        self.assertTrue(samples.filter(places__year__lt=0).exists())      # BCE years survive
        call_command("seed_maps", "--clear", stdout=StringIO())
        self.assertFalse(HistoricalMap.objects.filter(is_sample=True).exists())


class SeedRegionsTests(TestCase):
    def test_seed_and_clear(self):
        from django.core.management import call_command
        from io import StringIO
        from .models import Person, Tree
        from .tree import compute_levels
        call_command("seed_regions", "--per-region", "3", stdout=StringIO())
        trees = Tree.objects.filter(owner__username__startswith="demo_")
        self.assertEqual(trees.count(), 14 * 3)
        regions = set(Person.objects.filter(added_by__username__startswith="demo_").values_list("birth_region", flat=True))
        self.assertGreaterEqual(len(regions), 14)
        joined = 0
        for i in range(1, 15):
            t1 = trees.get(owner__username__startswith=f"demo_r{i:02d}_", owner__username__endswith="_1")
            t2 = trees.get(owner__username__startswith=f"demo_r{i:02d}_", owner__username__endswith="_2")
            t3 = trees.get(owner__username__startswith=f"demo_r{i:02d}_", owner__username__endswith="_3")
            a, b, c = (set(compute_levels(t.root_person)[0]) for t in (t1, t2, t3))
            self.assertFalse(a & b)            # entered twice, not linked
            joined += bool(a & c)              # really joined
        self.assertGreaterEqual(joined, 12)
        call_command("seed_regions", "--clear", stdout=StringIO())
        self.assertFalse(Tree.objects.filter(owner__username__startswith="demo_").exists())
        self.assertFalse(Person.objects.filter(added_by__username__startswith="demo_").exists())


class PresenceAndTourTests(TestCase):
    def test_page_views_mark_people_online_and_logout_takes_them_off(self):
        from .models import UserProfile
        from .region_insights import live_counts
        user = User.objects.create_user("onlayn", password="parol123")
        UserProfile.objects.create(user=user, region="Xorazm viloyati", tour_done=True)
        self.client.post(reverse("login"), {"username": "onlayn", "password": "parol123"})
        self.client.get(reverse("my_trees"))
        self.assertTrue(UserProfile.objects.get(user=user).is_online)
        counts = live_counts({})
        self.assertEqual((counts["total"], counts["regions"]["Xorazm viloyati"]), (1, 1))
        self.client.post(reverse("logout"))
        self.assertFalse(UserProfile.objects.get(user=user).is_online)

    def test_guide_runs_for_new_accounts_until_finished(self):
        from .models import UserProfile
        self.client.post(reverse("register"), {
            "first_name": "Yangi", "username": "yangi_user", "password1": "parol123", "password2": "parol123",
        })
        user = User.objects.get(username="yangi_user")
        self.client.force_login(user)
        page = self.client.get(reverse("my_trees"))
        self.assertContains(page, "pending: true")
        self.assertContains(page, 'data-tour="nav-library"')
        self.assertEqual(self.client.get(reverse("tour_done")).status_code, 405)
        self.client.post(reverse("tour_done"))
        self.assertTrue(UserProfile.objects.get(user=user).tour_done)
        self.assertContains(self.client.get(reverse("my_trees")), "pending: false")


class OpenPagesAndSharingTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.owner = User.objects.create_user("tarix", password="x")
        self.temur = person("Amir", "Temur", birth_year="1336", death_year="1405", bio="Sarkarda.")
        self.shohrux = person("Shohrux", "Mirzo", birth_year="1377")
        family(self.temur, None, [self.shohrux])
        PersonStory.objects.create(person=self.shohrux, text="Hirot poytaxt bo'lgan.")
        self.tree = Tree.objects.create(owner=self.owner, root_person=self.temur, name="Temuriylar", kind="talimiy",
                                        visibility="public", is_featured=True, slug="temuriylar")
        self.family_root = person("Botir", "Karimov")
        self.family_tree = Tree.objects.create(owner=self.owner, root_person=self.family_root, name="Oilam",
                                               visibility="public", is_featured=True, slug="oilam")

    def test_open_pages_work_without_login_and_family_trees_never_open(self):
        self.assertEqual(self.client.get(reverse("landing")).status_code, 200)
        index = self.client.get(reverse("open_index"))
        self.assertContains(index, "Temuriylar")
        self.assertNotContains(index, "Oilam")
        page = self.client.get(reverse("open_tree", args=["temuriylar"]))
        self.assertContains(page, "Shohrux Mirzo")
        self.assertContains(page, 'application/ld+json')
        self.assertEqual(self.client.get(reverse("open_tree", args=["oilam"])).status_code, 404)
        self.tree.refresh_from_db()
        self.assertEqual(self.tree.public_views, 1)

        slug = f"{self.shohrux.pk}-shohrux-mirzo"
        person_page = self.client.get(reverse("open_person", args=["temuriylar", slug]))
        self.assertContains(person_page, "Hirot poytaxt")
        self.assertContains(person_page, "Amir Temur")                     # the father is linked
        wrong = self.client.get(reverse("open_person", args=["temuriylar", f"{self.shohrux.pk}-boshqa"]))
        self.assertRedirects(wrong, reverse("open_person", args=["temuriylar", slug]), status_code=301)
        stranger = self.client.get(reverse("open_person", args=["temuriylar", f"{self.family_root.pk}-botir-karimov"]))
        self.assertEqual(stranger.status_code, 404)                         # not in this tree

        sitemap = self.client.get(reverse("sitemap")).content.decode()
        self.assertIn("/shajaralar/temuriylar/", sitemap)
        self.assertIn(slug, sitemap)
        self.assertNotIn("oilam", sitemap)
        self.assertIn("Disallow: /boshqaruv/", self.client.get(reverse("robots")).content.decode())
        card = self.client.get(reverse("open_tree_card", args=["temuriylar"]))
        self.assertEqual((card.status_code, card["Content-Type"]), (200, "image/png"))

    def test_generation_share_card_hides_private_names(self):
        from . import share_cards
        private = Tree.objects.create(owner=self.owner, root_person=person("Maxfiy", "Oila"), name="Maxfiy oila nomi")
        token = share_cards.make_token("avlod", private.pk)
        page = self.client.get(reverse("share_avlod", args=[token]))
        self.assertContains(page, "7 avloddan 1 tasini")
        self.assertNotContains(page, "Maxfiy oila nomi")
        self.assertEqual(self.client.get(reverse("share_avlod_png", args=[token]))["Content-Type"], "image/png")
        self.assertEqual(self.client.get(reverse("share_avlod", args=["soxta-token"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("share_avlod", args=[share_cards.make_token("test", private.pk)])).status_code, 404)

    def test_finished_quiz_returns_a_share_link(self):
        import json as _json
        for i in range(6):
            child = person(f"Farzand{i}", "Temur", birth_year=str(1360 + i))
            family(self.shohrux, None, [child])
        self.client.force_login(self.owner)
        self.client.get(reverse("tree_quiz", args=[self.tree.url_key]))
        state = self.client.session[f"quiz:{self.tree.pk}"]
        data = None
        for i, answer in enumerate(state["answers"]):
            data = self.client.post(reverse("tree_quiz_answer", args=[self.tree.url_key]),
                                    _json.dumps({"q": i, "choice": answer}), content_type="application/json").json()
        self.assertTrue(data["done"])
        self.assertIn("/u/test/", data["share"]["url"])
        share = self.client.get(data["share"]["url"].split("testserver")[-1])
        self.assertContains(share, f"{data['total']}/{data['total']}")

    def test_admin_can_feature_only_public_learning_trees(self):
        staff = User.objects.create_user("seo_admin", password="x", is_staff=True)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("boshqaruv:seo")).status_code, 404)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("boshqaruv:seo")).status_code, 200)
        other = Tree.objects.create(owner=self.owner, root_person=person("Bobur"), name="Boburiylar",
                                    kind="talimiy", visibility="public")
        self.client.post(reverse("boshqaruv:seo"), {"tree": other.pk, "is_featured": "on", "slug": "",
                                                    "seo_description": "Bobur avlodlari"})
        other.refresh_from_db()
        self.assertEqual((other.is_featured, other.slug), (True, "boburiylar"))
        self.assertTrue(ActivityLog.objects.filter(action="admin_seo_update", tree=other).exists())
        self.family_tree.is_featured = False
        self.family_tree.save()
        self.client.post(reverse("boshqaruv:seo"), {"tree": self.family_tree.pk, "is_featured": "on", "slug": "oila2"})
        self.family_tree.refresh_from_db()
        self.assertFalse(self.family_tree.is_featured)
