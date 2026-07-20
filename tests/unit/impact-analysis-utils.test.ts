import { describe, it, expect } from 'vitest';
import {
  buildReverseMap,
  isLayoutFile,
  sanitizeFilePath,
  traceLayoutHierarchyUpward,
  traverseDependencyGraph,
  type DependencyGraph,
} from '../../lib/impact-analysis-utils';

describe('impact-analysis-utils tests', () => {
    describe('sanitizeFilePath', () => {
        it('should correctly sanitize and validate file paths', () => {
            expect(sanitizeFilePath('src/layouts/MainLayout.tsx')).toBe('src/layouts/MainLayout.tsx');
            expect(sanitizeFilePath('  src/pages/Home.tsx  ')).toBe('src/pages/Home.tsx');

            // Path traversal and absolute paths should be rejected (returning null)
            expect(sanitizeFilePath('/src/layouts/MainLayout.tsx')).toBeNull();
            expect(sanitizeFilePath('../etc/passwd')).toBeNull();
            expect(sanitizeFilePath('src/layouts/../../etc/passwd')).toBeNull();
            expect(sanitizeFilePath('http://example.com/layout.tsx')).toBeNull();
            expect(sanitizeFilePath('')).toBeNull();
            expect(sanitizeFilePath(null)).toBeNull();
            expect(sanitizeFilePath(undefined)).toBeNull();
        });
    });

    describe('traverseDependencyGraph', () => {
        it('should traverse and stop at match when stopAtMatch is set', () => {
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

            // Running traversal with stopAtMatch: true should stop once BlogLayout.tsx is visited (as it is a layout)
            const result = traverseDependencyGraph(
                ['src/components/Sidebar.tsx'],
                reverseMap,
                isLayoutFile,
                { stopAtMatch: true }
            );

            expect(result.collected).toEqual(['src/layouts/BlogLayout.tsx']);
        });

        it('should handle defensive invalid and malformed reverseMap scenarios gracefully', () => {
            // @ts-expect-error - testing invalid raw structure
            const result1 = traverseDependencyGraph(['src/components/Sidebar.tsx'], null, isLayoutFile);
            expect(result1.collected).toEqual([]);
            expect(result1.tracePaths).toEqual({});

            // @ts-expect-error - testing invalid string array entry
            const result2 = traverseDependencyGraph([123], {}, isLayoutFile);
            expect(result2.collected).toEqual([]);
            expect(result2.tracePaths).toEqual({});
        });
    });

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
