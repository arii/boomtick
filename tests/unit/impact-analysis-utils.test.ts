import { describe, it, expect } from 'vitest';
import {
  buildReverseMap,
  isLayoutFile,
  traceLayoutHierarchyUpward,
  type DependencyGraph,
} from '../../lib/impact-analysis-utils';

describe('impact-analysis-utils tests', () => {
    describe('isLayoutFile', () => {
        it('should correctly identify layout files', () => {
            expect(isLayoutFile('src/layouts/MainLayout.tsx')).toBe(true);
            expect(isLayoutFile('src/layouts/BlogLayout.ts')).toBe(true);
            expect(isLayoutFile('src/components/MyCustomLayout.tsx')).toBe(true);
            expect(isLayoutFile('src/components/SidebarLayout.jsx')).toBe(true);

            expect(isLayoutFile('src/components/Button.tsx')).toBe(false);
            expect(isLayoutFile('src/pages/Home.tsx')).toBe(false);
            expect(isLayoutFile('src/styles/tokens.css')).toBe(false);
        });
    });

    describe('traceLayoutHierarchyUpward', () => {
        it('should trace layouts upward when a child layout is changed directly', () => {
            const graph: DependencyGraph = {
                modules: [
                    {
                        source: 'src/layouts/MainLayout.tsx',
                        dependencies: [
                            { resolved: 'src/layouts/BlogLayout.tsx', module: '', dynamic: false }
                        ]
                    },
                    {
                        source: 'src/layouts/BlogLayout.tsx',
                        dependencies: [
                            { resolved: 'src/layouts/NestedLayout.tsx', module: '', dynamic: false }
                        ]
                    },
                    {
                        source: 'src/layouts/NestedLayout.tsx',
                        dependencies: []
                    }
                ]
            };

            const reverseMap = buildReverseMap(graph);
            const result = traceLayoutHierarchyUpward(['src/layouts/NestedLayout.tsx'], reverseMap);

            expect(result.sharedLayouts).toContain('src/layouts/BlogLayout.tsx');
            expect(result.sharedLayouts).toContain('src/layouts/MainLayout.tsx');
            expect(result.layoutTrace['src/layouts/NestedLayout.tsx']).toEqual([
                'src/layouts/BlogLayout.tsx',
                'src/layouts/MainLayout.tsx'
            ]);
        });

        it('should trace layouts upward when a component change affects a layout', () => {
            const graph: DependencyGraph = {
                modules: [
                    {
                        source: 'src/layouts/BlogLayout.tsx',
                        dependencies: [
                            { resolved: 'src/components/Sidebar.tsx', module: '', dynamic: false }
                        ]
                    },
                    {
                        source: 'src/layouts/MainLayout.tsx',
                        dependencies: [
                            { resolved: 'src/layouts/BlogLayout.tsx', module: '', dynamic: false }
                        ]
                    },
                    {
                        source: 'src/components/Sidebar.tsx',
                        dependencies: []
                    }
                ]
            };

            const reverseMap = buildReverseMap(graph);
            const result = traceLayoutHierarchyUpward(['src/components/Sidebar.tsx'], reverseMap);

            expect(result.sharedLayouts).toEqual(['src/layouts/MainLayout.tsx']);
            expect(result.layoutTrace['src/layouts/BlogLayout.tsx']).toEqual([
                'src/layouts/MainLayout.tsx'
            ]);
        });

        it('should protect against circular/cyclic layouts without infinite loops', () => {
            const graph: DependencyGraph = {
                modules: [
                    {
                        source: 'src/layouts/LayoutA.tsx',
                        dependencies: [
                            { resolved: 'src/layouts/LayoutB.tsx', module: '', dynamic: false }
                        ]
                    },
                    {
                        source: 'src/layouts/LayoutB.tsx',
                        dependencies: [
                            { resolved: 'src/layouts/LayoutA.tsx', module: '', dynamic: false }
                        ]
                    }
                ]
            };

            const reverseMap = buildReverseMap(graph);
            const result = traceLayoutHierarchyUpward(['src/layouts/LayoutA.tsx'], reverseMap);

            expect(result.sharedLayouts).toContain('src/layouts/LayoutB.tsx');
            expect(result.layoutTrace['src/layouts/LayoutA.tsx']).toEqual([
                'src/layouts/LayoutB.tsx'
            ]);
        });

        it('should return empty results for non-layout changes that do not affect any layout', () => {
            const graph: DependencyGraph = {
                modules: [
                    {
                        source: 'src/pages/Home.tsx',
                        dependencies: [
                            { resolved: 'src/components/Button.tsx', module: '', dynamic: false }
                        ]
                    },
                    {
                        source: 'src/components/Button.tsx',
                        dependencies: []
                    }
                ]
            };

            const reverseMap = buildReverseMap(graph);
            const result = traceLayoutHierarchyUpward(['src/components/Button.tsx'], reverseMap);

            expect(result.sharedLayouts).toEqual([]);
            expect(result.layoutTrace).toEqual({});
        });
    });

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
