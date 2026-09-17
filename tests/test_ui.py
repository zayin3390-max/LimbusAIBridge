import copy
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from bridge.core import Entry, BridgeError
from bridge.ui_model import DraftStore, matches, selected, preview
from test_bridge import Fixture

def entry(uid='one', **changes):
    row=Entry(uid,'Skills_personality.json',(),('dataList',0,'desc'),'desc','Gain 3 [Binding].',None,'missing',True,newly_seen=True)
    for key,value in changes.items():setattr(row,key,value)
    return row

class ViewModelTests(unittest.TestCase):
    def test_new_view_excludes_cached_ignored_and_historical(self):
        for row in [entry(status='cached'),entry(status='ignored'),entry(newly_seen=False)]:
            self.assertFalse(matches(row,'本次更新',{'人格'}))
        self.assertTrue(matches(entry(),'本次更新',{'人格'}))

    def test_failure_view_includes_old_failures(self):
        self.assertTrue(matches(entry(status='failed',newly_seen=False),'失败项',{'人格'}))
        self.assertFalse(matches(entry(),'失败项',{'人格'}))

    def test_search_includes_edited_translation_and_category(self):
        row=entry(translation='束缚')
        self.assertTrue(matches(row,'所有条目',{'人格'},'束缚'))
        self.assertTrue(matches(row,'所有条目',{'人格'},'GAIN'))
        self.assertFalse(matches(row,'所有条目',{'敌方'},'束缚'))

    def test_selection_not_limited_to_visible_filter(self):
        rows=[entry('one'),entry('two',file='Enemies.json'),entry('saved',status='cached'),entry('ignored',status='ignored')]
        self.assertEqual([e.uid for e in selected(rows,{e.uid for e in rows})],['one','two'])

    def test_preview_hides_engine_tags_and_limits_length(self):
        row=entry(source='<color=#fff>Long\n  text</color> Gain 3 [Binding]. '+('a'*120))
        self.assertNotIn('<',preview(row))
        self.assertIn('3 [Binding]',preview(row))
        self.assertNotIn('\n',preview(row))
        self.assertLessEqual(len(preview(row)),95)

class DraftTests(Fixture):
    def test_drafts_survive_restart_without_becoming_translation(self):
        row=entry();store=DraftStore(self.data);store.remember(row,'获得3层[Binding]。');store.save()
        self.assertEqual(DraftStore(self.data).get(row),'获得3层[Binding]。')
        self.cache.load([row]);self.assertEqual(row.status,'pending');self.assertEqual(row.translation,'')

    def test_changed_source_or_reference_does_not_reuse_draft(self):
        row=entry();store=DraftStore(self.data);store.remember(row,'旧草稿')
        changed=copy.deepcopy(row);changed.source='New text'
        self.assertIsNone(store.get(changed))
        changed=copy.deepcopy(row);changed.refs={'kr':'변경'}
        self.assertIsNone(store.get(changed))
        self.assertEqual(store.get(row),'旧草稿')

    def test_corrupt_draft_file_preserved(self):
        path=self.data/'editor-drafts.json';original=b'{broken';path.write_bytes(original)
        store=DraftStore(self.data);store.remember(entry(),'新草稿')
        with self.assertRaises(BridgeError):store.save()
        self.assertEqual(path.read_bytes(),original)

    def test_saved_text_discards_redundant_draft(self):
        row=entry(translation='译文');store=DraftStore(self.data)
        store.remember(row,'修改');store.remember(row,'译文');store.save()
        self.assertIsNone(DraftStore(self.data).get(row))

class GuiTests(Fixture):
    """Exercise withdrawn widgets directly. No desktop input or API requests."""
    def setUp(self):
        super().setUp()
        import tkinter as tk
        from bridge import settings
        from bridge.gui import App
        try:
            self.window=tk.Tk();self.window.withdraw()
        except tk.TclError as exc:
            super().tearDown();self.skipTest(str(exc))
        config=dict(settings.DEFAULTS,game_path=str(self.game))
        with patch('bridge.gui.settings.load',return_value=(config,'')):
            self.app=App(self.window,self.data,autostart=False)
        self.app.monitor_var.set(False)
        scan=self.scan()
        for row in scan.entries:row.newly_seen=True
        self.app.scanned(scan)
        self.window.update_idletasks()

    def tearDown(self):
        for token in self.window.tk.call('after','info'):self.window.after_cancel(token)
        self.window.destroy()
        super().tearDown()

    def pick(self,predicate=lambda row:True):
        iid=next(i for i,e in self.app.visible.items() if predicate(e))
        self.app.tree.selection_set(iid);self.app.show_entry()
        return self.app.current

    def edit(self,text):
        self.app.translation.delete('1.0','end');self.app.translation.insert('1.0',text)
        self.app.editor_changed()

    def test_pages_and_empty_buttons(self):
        self.app.scan=None;self.app.refresh()
        self.assertEqual(len(self.app.pages),3)
        self.assertTrue(self.app.translate_button.instate(['disabled']))
        self.assertTrue(self.app.build_button.instate(['disabled']))
        self.assertEqual(self.app.empty_title.get(),'先扫描游戏内容')

    def test_draft_survives_filter_and_selection_changes(self):
        first=self.pick();self.edit('草稿内容')
        self.app.choose_mode('已有译文')
        self.app.choose_mode('本次更新')
        self.pick(lambda row:row.uid==first.uid)
        self.assertEqual(self.app.translation.get('1.0','end-1c'),'草稿内容')
        self.app.flush_drafts()
        self.assertEqual(DraftStore(self.data).get(first),'草稿内容')
        self.assertEqual(first.translation,'')

    def test_bad_manual_translation_stays_as_draft(self):
        row=self.pick(lambda row:row.field=='desc')
        self.edit('失去数字和标签');self.app.save_manual()
        self.assertEqual(row.status,'pending')
        self.assertEqual(self.app.translation.get('1.0','end-1c'),'失去数字和标签')
        self.assertNotEqual(self.app.api_status.get(),'')
        self.assertTrue(self.app.save_button.instate(['!disabled']))

    def test_valid_manual_translation_saved_and_draft_removed(self):
        row=self.pick(lambda row:row.field=='desc')
        self.edit('获得3层[Binding]。');self.app.save_manual()
        self.assertEqual(row.status,'cached')
        self.assertIsNone(DraftStore(self.data).get(row))
        self.app.choose_mode('已有译文');self.pick(lambda e:e.uid==row.uid)
        self.assertEqual(self.app.translation.get('1.0','end-1c'),row.translation)

    def test_revert_restores_last_saved_text(self):
        row=self.pick();self.edit('草稿');self.app.revert_draft()
        self.assertEqual(self.app.translation.get('1.0','end-1c'),row.translation)
        self.assertIsNone(self.app.drafts.get(row))
        self.assertTrue(self.app.save_button.instate(['disabled']))

    def test_backend_updates_do_not_create_stale_drafts(self):
        row=self.pick()
        row.translation='新保存的内容';row.status='cached'
        self.app.choose_mode('所有条目')
        self.pick(lambda e:e.uid==row.uid)
        self.assertIsNone(self.app.drafts.get(row))
        self.assertEqual(self.app.translation.get('1.0','end-1c'),row.translation)

    def test_selection_retained_across_categories(self):
        initial={row.uid for row in self.app.selected_entries()}
        self.app.category.set('卡池');self.app.category_changed()
        self.assertEqual({row.uid for row in self.app.selected_entries()},initial)
        self.assertIn('筛选外',self.app.selected_var.get())

    def test_paging_limits_rendered_rows_and_selects_all_results(self):
        self.app.scan.entries=[entry(str(i)) for i in range(450)]
        self.app.checked.clear();self.app.refresh()
        self.assertEqual(len(self.app.tree.get_children()),200)
        self.app.select_visible();self.assertEqual(len(self.app.checked),200)
        self.app.change_page(2);self.assertEqual(len(self.app.tree.get_children()),50)
        self.app.select_filtered();self.assertEqual(len(self.app.checked),450)
        self.app.search.set('no matches');self.app.filter_changed()
        self.assertEqual(len(self.app.visible),0)
        self.assertEqual(len(self.app.selected_entries()),450)
        self.app.clear_visible();self.assertEqual(len(self.app.selected_entries()),0)

    def test_ignore_and_restore_preserve_cached_translation(self):
        row=self.pick(lambda row:row.field=='desc')
        self.app.cache.put(row,'获得3层[Binding]。','manual')
        self.app.checked={row.uid};self.app.ignore_checked();self.assertEqual(row.status,'ignored')
        self.app.choose_mode('已忽略');self.app.select_visible();self.app.unignore_checked()
        self.assertEqual(row.status,'cached');self.assertEqual(row.translation,'获得3层[Binding]。')

    def test_cached_rows_can_be_selected_for_explicit_retranslation(self):
        row=self.pick(lambda row:row.field=='desc')
        self.app.cache.put(row,'获得3层[Binding]。','old-model')
        self.app.checked.clear();self.app.choose_mode('已有译文')
        self.app.select_visible()
        self.assertEqual(self.app.selected_retranslations(),[row])
        self.assertEqual(self.app.selected_entries(),[])
        self.assertTrue(self.app.retranslate_button.instate(['!disabled']))
        self.assertTrue(self.app.translate_button.instate(['disabled']))
        self.assertIn('重译 1 条',self.app.selected_var.get())
        with patch.object(self.app,'collect_settings',return_value=({'api_base':'http://localhost/v1','model':'fake'},'')):
            with patch.object(self.app,'run') as run:
                self.app.start_retranslate()
        self.assertEqual(run.call_args.args[2],'重译')
        self.assertIsNone(run.call_args.args[3])

    def test_retranslation_failures_visible_without_losing_cached_text(self):
        row=self.pick(lambda row:row.field=='desc')
        self.app.cache.put(row,'获得3层[Binding]。','old-model')
        row.retranslation_error='重译失败；旧译文已保留'
        self.app.choose_mode('失败项');self.app.clear_visible();self.app.select_filtered()
        self.assertEqual(self.app.selected_retranslations(),[row])
        self.pick(lambda e:e.uid==row.uid)
        self.assertEqual(self.app.translation.get('1.0','end-1c'),'获得3层[Binding]。')
        self.assertIn('旧译文已保留',self.app.detail_var.get())
        self.app.busy=True;self.app.update_actions()
        self.assertTrue(self.app.retranslate_button.instate(['disabled']))

    def test_busy_state_locks_editor_and_api_fields(self):
        self.pick();self.edit('草稿')
        self.app.busy=True;self.app.update_actions()
        self.assertTrue(self.app.translate_button.instate(['disabled']))
        self.assertTrue(self.app.key_entry.instate(['disabled']))
        self.assertEqual(self.app.translation.cget('state'),'disabled')
        self.app.busy=False;self.app.update_actions()
        self.assertTrue(self.app.key_entry.instate(['!disabled']))
        self.assertTrue(self.app.save_button.instate(['!disabled']))

    def test_startup_schedules_cache_restore_never_scan_or_watch(self):
        from bridge.gui import App
        from bridge import settings
        import tkinter as tk
        known_timers=set(self.window.tk.call('after','info'))
        window=tk.Toplevel(self.window);window.withdraw()
        scheduled=[]
        original=window.after
        def record(delay,fn=None,*args):
            scheduled.append((delay,getattr(fn,'__name__','')))
            return original(delay,fn,*args)
        with patch.object(window,'after',side_effect=record), \
             patch('bridge.gui.settings.load',return_value=(dict(settings.DEFAULTS,game_path=str(self.game),monitor=True),'')):
            app=App(window,self.data,autostart=True)
        names=[name for _,name in scheduled]
        self.assertIn('restore_scan',names)
        self.assertNotIn('start_scan',names)
        self.assertNotIn('watch',names)
        self.assertFalse(app.monitor_var.get())
        for token in set(window.tk.call('after','info'))-known_timers:window.after_cancel(token)
        window.destroy()

    def test_restore_scan_only_uses_snapshot_and_latest_translations(self):
        from bridge.scan_cache import save_scan
        save_scan(self.app.scan,self.data)
        with patch('bridge.gui.scan_game',side_effect=AssertionError('No full scan')):
            self.app.restore_scan();self.app.worker.join(timeout=10);self.app.poll()
        self.assertIn('已读取缓存',self.app.status.get())
        self.assertIsNotNone(self.app.scan)

    def test_compact_layout_keeps_retranslation_and_report_in_menu(self):
        with patch.object(self.window,'winfo_width',return_value=420), \
             patch.object(self.window,'winfo_height',return_value=360):
            self.app.adapt_layout()
        hidden=self.app.command_panels['work'].hidden
        self.assertIn(self.app.retranslate_button,hidden)
        self.assertIn(self.app.report_button,hidden)
        self.assertNotIn(self.app.overflow_button,hidden)
        self.assertEqual(self.app.overflow_menu.entrycget(0,'label'),'重译所选')
        self.assertEqual(self.app.overflow_menu.entrycget(1,'label'),'导出报告')

    def test_invalid_api_numbers_do_not_block_scan(self):
        self.app.api_vars['retries'].set('not a number')
        with patch.object(self.app,'run') as runner:
            self.app.start_scan()
        self.assertEqual(runner.call_count,1)
        self.assertEqual(runner.call_args.args[2],'扫描')

    def test_setting_bounds_and_connection_key_mask(self):
        self.assertEqual(self.app.key_entry.cget('show'),'●')
        self.app.toggle_key();self.assertEqual(self.app.key_entry.cget('show'),'')
        self.app.toggle_key();self.assertEqual(self.app.key_entry.cget('show'),'●')
        self.app.api_vars['retries'].set('11')
        with self.assertRaises(BridgeError):self.app.collect_settings()

    def test_logs_hide_both_saved_and_unsaved_keys(self):
        self.app.api_key='saved-test-key';self.app.key_var.set('new-test-key')
        self.app.show_error('saved-test-key and new-test-key')
        for text in (self.app.status.get(),self.app.log.get('1.0','end'),self.app.api_status.get(),
                     (self.data/'activity.log').read_text(encoding='utf-8')):
            self.assertNotIn('saved-test-key',text);self.assertNotIn('new-test-key',text)

    def test_done_callback_can_start_followup_task(self):
        def callback(result):
            self.app.busy=True
        self.app.events.put(('done',(callback,None)));self.app.poll()
        self.assertTrue(self.app.busy)
        self.assertTrue(self.app.scan_button.instate(['disabled']))

    def test_local_scan_does_not_mutate_fixture_files(self):
        before={str(p):p.read_bytes() for p in self.game.rglob('*') if p.is_file()}
        self.app.start_scan();self.app.worker.join(timeout=10);self.app.poll()
        self.assertFalse(self.app.busy)
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.game.rglob('*') if p.is_file()})

    def test_existing_exploration_gap_appears_without_new_update(self):
        row=entry('rpg-gap',file='RPGSystem/rpg-loc-dialogue-floor-1.json',newly_seen=False,field='text')
        self.app.scan.entries=[row]
        self.app.scanned(self.app.scan)
        self.assertEqual(self.app.mode.get(),'待补译')
        self.assertEqual(len(self.app.visible),1)
        self.assertEqual(self.app.selected_entries(),[row])
        self.assertTrue(self.app.translate_button.instate(['!disabled']))
        self.app.choose_mode('本次更新')
        self.assertEqual(len(self.app.visible),0)
        self.app.choose_mode('缺漏补查')
        self.assertEqual(len(self.app.visible),1)

    def test_advanced_and_log_sections_toggle(self):
        self.app.toggle_advanced();self.assertTrue(self.app.advanced_open)
        self.app.toggle_advanced();self.assertFalse(self.app.advanced_open)
        self.app.toggle_log();self.assertTrue(self.app.log_open)
        self.app.toggle_log();self.assertFalse(self.app.log_open)

if __name__=='__main__':unittest.main()
