import { describe, it, expect } from 'vitest';
import {
  buildReverseMap,
  type DependencyGraph,
} from '../../lib/impact-analysis-utils';

describe('impact-analysis-utils tests', () => {
    it('test buildReverseMap with CSS @import edges natively generated', () => {
        const graph: DependencyGraph = {
            modules: [
                {
                    source: 'src/components/Button.tsx',
                    dependencies: [
                        { resolved: 'src/styles/tokens.css', module: '', dynamic: false }
                    ]
                },
                {
                    source: 'src/styles/tokens.css',
                    dependencies: [
                        { resolved: 'src/styles/colors.css', module: '', dynamic: false }
                    ]
                },
                {
                    source: 'src/styles/colors.css',
                    dependencies: []
                }
            ]
        };

        const reverseMap = buildReverseMap(graph);

        expect(reverseMap['src/styles/tokens.css']).toEqual([{ source: 'src/components/Button.tsx', dynamic: false }]);
        expect(reverseMap['src/styles/colors.css']).toEqual([{ source: 'src/styles/tokens.css', dynamic: false }]);
    });
});
