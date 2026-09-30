declare namespace JSX {
  interface Element {}
  interface ElementClass { render: any; }
  interface ElementAttributesProperty { props: {}; }
  interface ElementChildrenAttribute { children: {}; }
  interface IntrinsicAttributes { key?: string | number; }
  interface IntrinsicElements { [elementName:string]: any; }
}
