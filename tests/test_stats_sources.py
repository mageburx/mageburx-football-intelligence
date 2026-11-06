import unittest
from scripts.assess_stats_sources import assess, FIELDS, SOURCE

class StatSourceTests(unittest.TestCase):
    def setUp(self):
        self.urls = []
    def fake(self,url):
        self.urls.append(url)
        if url.endswith('/season.json'):
            return {'meta':{'license':'CC BY 4.0','temporal_coverage':'2026-08-01/2026-11-02'},
                    'matches':[{'id':'fixture-a','dataset_url':SOURCE+'/football/matches/a/data.json'},
                               {'id':'fixture-b','dataset_url':SOURCE+'/football/matches/b/data.json'}]}
        if url.endswith('a/data.json'):
            return {'meta':{'license':'CC BY 4.0'},
                    'statistics':[{'label':k,'home':4,'away':6} for k in FIELDS]}
        if url.endswith('b/data.json'):
            return {'meta':{'license':'CC BY 4.0'},
                    'statistics':[{'label':k,'home':0,'away':3} for k in FIELDS]}
        raise ValueError('not found')

    def test_license_and_stat_sample(self):
        report=assess(fetcher=self.fake,sleep=lambda s:None,sample_per_league=2)
        self.assertEqual(report['leagues']['pt']['status'],'sample_available')
        self.assertEqual(report['leagues']['dk']['status'],'sample_available')
        self.assertEqual(report['leagues']['pt']['sample_checked'],2)
        self.assertEqual(report['leagues']['dk']['stats_fields_validated']['Corners'],2)
        self.assertEqual(len(self.urls),6)
        self.assertNotIn('matches',report['leagues']['dk'])
        self.assertIn('rights_note',report['source'])

    def test_no_false_zeros_for_missing_stats(self):
        def partial(url):
            if url.endswith('/season.json'):
                return {'meta':{'license':'CC BY 4.0'},
                        'matches':[{'id':'a','dataset_url':SOURCE+'/football/a/data.json'}]}
            return {'meta':{'license':'CC BY 4.0'},
                    'statistics':[{'label':'Corners','home':None,'away':0}]}
        report=assess(fetcher=partial,sleep=lambda s:None,sample_per_league=1)
        self.assertEqual(report['leagues']['pt']['status'],'sample_incomplete')
        self.assertEqual(report['leagues']['pt']['stats_fields_validated']['Corners'],0)
        self.assertEqual(report['leagues']['pt']['sample_checked'],1)

    def test_rejects_unlicensed_or_duplicate_records(self):
        def bad(url):
            return {'meta':{'license':'unlicensed'},'matches':[{'id':'a'}]}
        report=assess(fetcher=bad,sleep=lambda s:None)
        self.assertEqual(report['leagues']['dk']['status'],'unavailable')
        self.assertEqual(report['leagues']['dk']['sample_checked'],0)

if __name__ == '__main__':
    unittest.main()
